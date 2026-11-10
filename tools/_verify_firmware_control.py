import sys,struct,json,importlib.util
from pathlib import Path
sys.path.insert(0,'vendor/pi32v2-isa')
spec=importlib.util.spec_from_file_location('m82sim','vendor/pi32v2-isa/tools/llvm/sim.py')
sim=importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
# Upstream m2.py refers to an author's absolute-path ID list that is absent.
# Load the other published models, then derive missing memory-form IDs from
# the published ISA table. Leave upstream files unchanged.
def portable_models():
    import importlib,types
    models={}
    for p in sorted(Path('vendor/pi32v2-isa/tools/hwtest/semantics').glob('*.py')):
        if p.name.startswith('_') or p.stem=='m2': continue
        models.update(importlib.import_module('semantics.'+p.stem).MODELS)
    m=types.ModuleType('m82_memory_models'); m.__file__=str(Path('vendor/pi32v2-isa/tools/hwtest/semantics/m2.py').resolve())
    source=Path('vendor/pi32v2-isa/tools/hwtest/semantics/m2.py').read_text()
    source=source.replace('open("/root/.t3/projects/pi32v2-isa-wt/ids5-m.txt").read().split()', '[]')
    exec(source,m.__dict__)
    models.update({k:v for k,v in m.MODELS.items() if k not in models})
    for ins in sim.table.load().insns:
        i=ins.id
        if i in models: continue
        if i.startswith(('ld.','st.')) and not i.startswith(('ld.w.npc','st.w.modimm')):
            models[i]=m.memop(i)
        elif i.startswith('rmw.'): models[i]=m.rmw(i)
    return models
sim.check.load_models=portable_models
tests=[]
def run(name,request,online=True,fallback=False):
    cpu=sim.CPU(); symbols=cpu.load_elf(Path('build/usb_clock.elf').read_bytes())
    cpu.pc=symbols['usb_probe']; cpu.rets=sim.RETURN
    original_sp=cpu.sp
    cpu.R[0]=0x20000; cpu.R[1]=0x21000 if request is not None else 0xffffffff
    if request is not None: cpu.mem.write(0x21000,request)
    old=bytearray(0x46586); old[0x46554:0x46586]=bytes.fromhex(Path('firmware/hid-input-prefix.hex').read_text()); old[0x4626d:0x46276]=bytes.fromhex('092100010001220000')
    cpu.mem.write(31744877,old[31744877-0x1e00100:31744877-0x1e00100+9])
    cpu.mem.write(86128+204,struct.pack('<I',0x23000 if online else 0))
    captured=None
    for _ in range(500):
        if cpu.pc==sim.RETURN: break
        if cpu.pc==symbols['resume_hid']:
            assert fallback, name
            assert cpu.R[4]==0x20000 and cpu.R[5]==(0x21000 if request is not None else 0xffffffff)
            assert cpu.sp==original_sp-16 # rets + r6,r5,r4
            tests.append({'case':name,'result':'delegated to original handler'}); return
        if cpu.pc==symbols['dev_ioctl']:
            assert cpu.R[0]==0x23000 and cpu.R[1]==19
            cpu.mem.write(cpu.R[2],struct.pack('<HHBBBBB',0,2026,11,9,15,45,30))
            cpu.R[0]=0; cpu.pc=cpu.rets; continue
        if cpu.pc==symbols['hid_endpoint_init']:
            assert cpu.R[0]==0x20000
            cpu.R[0]=0; cpu.pc=cpu.rets; continue
        if cpu.pc==symbols['usb_payload']:
            assert cpu.R[0]==0x20000 and cpu.R[1]==0x21000
            captured=cpu.mem.read(cpu.R[2],cpu.R[3]); cpu.mem.write(0x22000,captured)
            cpu.R[0]=0x22000; cpu.pc=cpu.rets; continue
        cpu.step()
    else: raise AssertionError('Execution did not terminate: '+name)
    assert not fallback and cpu.sp==original_sp and cpu.R[0]==0,name
    if name=='report_descriptor':
        assert captured[:50]==old[0x46554:0x46554+50] and captured[-17:]==bytes.fromhex('0600ff0901150026ff0075089510b102c0')
    elif name=='hid_descriptor':
        assert cpu.mem.read(0x22000+7,2)==b'\x43\x00'
    elif name=='rtc_online':
        assert captured[:6]==b'M82T\x02\x00'
        assert struct.unpack_from('<HBBBBB',captured,6)==(2026,11,9,15,45,30)
    elif name=='rtc_absent': assert captured[:6]==b'M82T\x02\x01'
    tests.append({'case':name,'result':'passed','payload_hex':captured.hex()})
def req(typ,op,val,length): return struct.pack('<BBHHH',typ,op,val,3,length)
run('report_descriptor',req(0x81,6,0x2200,255))
run('hid_descriptor',req(0x81,6,0x2100,9))
run('rtc_online',req(0xa1,1,0x300,16))
run('rtc_absent',req(0xa1,1,0x300,16),online=False)
run('set_report_input_untouched',req(0x21,9,0x100,16),fallback=True)
run('short_get_report',req(0xa1,1,0x300,8),fallback=True)
run('other_report_type',req(0xa1,1,0x100,16),fallback=True)
run('vendor_request',req(0xc1,1,0x300,16),fallback=True)
run('reset_sentinel',None,fallback=True)
cpu=sim.CPU(); cpu.rets=sim.RETURN; cpu.pc=0x1e328f8
cpu.R[0]=0; cpu.R[1]=0x25000; cpu.R[2]=0x26000
cpu.mem.write(0x26000,struct.pack('<I',3))
from mivo_m82.bundle import FirmwareBundle; sys.path.insert(0,'vendor/jl-misctools/firmware'); from jltech.cipher import jl_sfc_cipher; sector=next(s for s in FirmwareBundle().sectors if s.offset==0x34000); scratch=bytearray(0x35000); scratch[0x34000:0x35000]=sector.data; jl_sfc_cipher(scratch,0x34000,4096,0x2000,0x77a); app=bytearray(0x33000); app[0x31f00:0x32f00]=scratch[0x34000:0x35000]
cpu.mem.write(0x1e00100,app)
for _ in range(300):
    if cpu.pc==sim.RETURN: break
    if cpu.pc in [0x1e328c0,0x1e328dc]:
        cpu.R[0]=cpu.R[1]; cpu.pc=cpu.rets; continue
    cpu.step()
else: raise AssertionError('Configuration descriptor did not return')
assert cpu.R[0]==25 and cpu.mem.read(0x25000+16,2)==b'\x43\x00'
assert cpu.mem.read(0x26000,4)==struct.pack('<I',4)
tests.append({'case':'configuration_descriptor_advertises_67_bytes','result':'passed'})
Path('build/control-validation.json').write_text(json.dumps({'scope':'PI32v2 simulator with mocked firmware APIs; no hardware validation','cases':tests},indent=2))
print('Passed',len(tests),'simulated control-transfer cases')
