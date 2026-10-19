"""Model actual EE hook instructions, delay slots and C-call register clobbers.

This is an instruction-level ABI fixture, not MIPS execution or console evidence.
Native GCC/LLVM CI still verifies assembly and linking.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'ee_core/src/asm.S').read_text()
source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
SYMS = {'_end': 0x90000, '_gp': 0x81234, 'disable_padOpen_hook': 0x100,
        'padOpen_hooked': 0x108, 'g_compat_mask': 0x110,
        'Old_CreateThread': 0x118, 'Old_ExecPS2': 0x120}
MASK = (1 << 64) - 1
CALLER = ['a0','a1','a2','a3','t0','t1','t2','t3','v0','v1','ra']

def run(name, *, result=1, disabled=0, hooked=0, priority=0, current=0, compat=0, entry=0x200000):
    body = source.split(name + ':', 1)[1].split('.end    ' + name, 1)[0]
    instructions, labels = [], {}
    for line in body.splitlines():
        line = re.split(r'//|#', line)[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            labels[line[:-1]] = len(instructions)
        else:
            instructions.append(line)
    regs = {r: 0x10000000 + i * 0x100 for i,r in enumerate(CALLER + ['sp','gp','s0','s1','s2','s3','s4'])}
    regs.update(zero=0, sp=0x70000, gp=0x345678, ra=0x777777, a0=0x40000)
    if name == 'Hook_ExecPS2':
        regs['a0'] = entry
    initial = regs.copy()
    memory = {SYMS['disable_padOpen_hook']: disabled, SYMS['padOpen_hooked']: hooked,
              SYMS['g_compat_mask']: compat, SYMS['Old_CreateThread']: 0xabc0,
              SYMS['Old_ExecPS2']: 0xabc8, regs['a0']+0x14: priority, regs['a0']+0x18: current}
    calls, stores = [], []
    def value(s):
        s=s.strip()
        if s.startswith('$'): return regs[s[1:]]
        if s=='PADOPEN_HOOK': return 0
        if s=='COMPAT_MODE_6': return 0x20
        if s in SYMS: return SYMS[s]
        return int(s,0)
    def address(s):
        m=re.fullmatch(r'([^()]*)\((\$\w+)\)',s)
        return value(m[1])+value(m[2]) if m else value(s)
    def plain(line):
        op, *tail=line.split(None,1)
        args=[x.strip() for x in tail[0].split(',')] if tail else []
        if op=='nop': return
        if op in ('la','lui'):
            regs[args[0][1:]]=value(args[1]) << (16 if op=='lui' else 0)
        elif op in ('daddu','addiu','andi','sltu','slti'):
            a,b=value(args[1]),value(args[2])
            regs[args[0][1:]]={'daddu':lambda:a+b,'addiu':lambda:a+b,'andi':lambda:a&b,
                                    'sltu':lambda:int(a<b),'slti':lambda:int(a<b)}[op]() & MASK
        elif op in ('sd','sw'):
            loc=address(args[1]); memory[loc]=value(args[0]);stores.append((loc,8 if op=='sd' else 4))
        elif op in ('ld','lw'):
            regs[args[0][1:]]=memory[address(args[1])]
        else: raise AssertionError(('unsupported instruction',line))
    pc=0
    for _ in range(160):
        line=instructions[pc]; op=line.split()[0]
        if op in ('bne','beq'):
            a,b,target=[x.strip() for x in line.split(None,1)[1].split(',')]
            take=(value(a)!=value(b)) if op=='bne' else (value(a)==value(b))
            plain(instructions[pc+1]); pc=labels[target[:-1]] if take else pc+2
        elif op=='jal':
            target=line.split()[1];plain(instructions[pc+1]);calls.append(target)
            assert regs['gp']==SYMS['_gp'], (name,target,'wrong C global pointer')
            assert regs['sp']%16==0
            if target=='Install_PadOpen_Hook':
                assert [regs[r] for r in ('a0','a1','a2')]==[0x100000,0x1ff0000,0]
            if target=='InitRegsExecPS2':
                assert [regs[r] for r in ('a0','a1','a2','a3')]==[initial[r] for r in ('a0','a1','a2','a3')]
                regs['gp']=0  # the real non-returning ExecPS2 register scrub clears it
            else:
                if target=='New_SifSetDma': assert regs['a0']==initial['a0'] and regs['a1']==initial['a1']
                for r in CALLER: regs[r]=0xdead0000+CALLER.index(r)
                regs['v0']=result
            pc+=2
        elif op=='jr':
            dest=value(line.split()[1]);plain(instructions[pc+1]);break
        else:
            plain(line);pc+=1
    else: raise AssertionError('hook did not terminate')
    if name=='_SifSetDma':
        assert dest==initial['ra'] and regs['sp']==initial['sp'] and regs['gp']==initial['gp']
        assert regs['v0']==result
        frame=0x20
    elif name=='Hook_CreateThread':
        assert dest==0xabc0
        if calls:
            for r in ('sp','gp','ra','a0','a1','a2','a3','t0','t1','t2','t3'):
                assert regs[r]==initial[r],(name,r)
            assert memory[SYMS['padOpen_hooked']]==result
        else:
            for r in ('sp','gp','a0','a1','a2','a3','t0','t1','t2','t3'):
                assert regs[r]==initial[r],(name,'bypass',r)
        frame=0x60
    else:
        assert dest==0xabc8
        assert [regs[r] for r in ('a0','a1','a2','a3')]==[initial[r] for r in ('a0','a1','a2','a3')]
        frame=0
    for loc,width in stores:
        if loc==SYMS['padOpen_hooked'] and width==4 and name in ('Hook_CreateThread','Hook_ExecPS2'):
            continue
        assert SYMS['_end']-frame<=loc and loc+width<=SYMS['_end'],(name,'frame overflow',loc)
    return calls

for result in (0,1):
    assert run('_SifSetDma',result=result)==['New_SifSetDma']
    for priority in (0,1,4):
        assert run('Hook_CreateThread',result=result,priority=priority)==['Install_PadOpen_Hook']
for args in ({'disabled':1},{'hooked':1},{'priority':5},{'priority':1,'current':2}):
    assert run('Hook_CreateThread',**args)==[]
assert run('Hook_ExecPS2')==['Reset_Padhook','Install_PadOpen_Hook','InitRegsExecPS2']
assert run('Hook_ExecPS2',compat=0x20)==[]
assert run('Hook_ExecPS2',entry=0x80000)==[]
# Prove both sides of the frame are enforced, including stores below the former cutoff.
valid_source = source
for offset in ('-0x200', '0x0020'):
    source = valid_source.replace('sd      $ra, 0x0000($sp)',
                                 f'sd      $t0, {offset}($sp)\n    sd      $ra, 0x0000($sp)', 1)
    assert source != valid_source
    try:
        run('_SifSetDma')
    except AssertionError as error:
        assert 'frame overflow' in str(error), error
    else:
        raise AssertionError(('out-of-frame store accepted', offset))
source = valid_source
print('PASS: EE hook GP context, caller registers, delay slots, stack bounds, bypass and DMA return preservation')
