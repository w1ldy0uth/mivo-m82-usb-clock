import runpy,struct,json
from pathlib import Path
import os,sys; ROOT=Path(__file__).resolve().parent.parent; os.chdir(ROOT); sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tools')); from assemble import assemble; assemble(); ctx=runpy.run_path('tools/_verify_firmware_control.py'); sim=ctx['sim']; tests=ctx['tests']
models=sim.check.load_models(); sim.check.load_models=lambda:models
def packet(year=2026,month=11,day=9,hour=16,minute=40,second=0):
    return b'M82T\x01\x01'+struct.pack('<HBBBBB',year,month,day,hour,minute,second)+b'\x00'*3
def case(name,data,valid=False,queue_error=False,busy=False):
    cpu=sim.CPU(); syms=cpu.load_elf(Path('build/usb_clock.elf').read_bytes())
    cpu.pc=syms['receive_time']; cpu.rets=sim.RETURN
    sp=cpu.sp; cpu.mem.write(86128+204,struct.pack('<I',0x23000))
    cpu.mem.write(0x1e460b3,b'app_core\x00')
    cpu.mem.write(0x16818,struct.pack('<I',int(busy)))
    queued=[]; applied=[]
    def step():
        if cpu.pc==syms['usb_read_ep0']:
            assert cpu.R[0]==0 and cpu.R[2]==16
            cpu.mem.write(cpu.R[1],data); cpu.R[0]=cpu.R[1]; cpu.pc=cpu.rets
        elif cpu.pc==0x1716a:
            assert cpu.mem.read(cpu.R[0],9)==b'app_core\x00'
            assert cpu.R[1]==0x300000 and cpu.R[2]==3
            vec=struct.unpack('<III',cpu.mem.read(cpu.R[3],12))
            assert vec==(syms['apply_time'],1,0x1680c)
            queued.append(vec); cpu.R[0]=1 if queue_error else 0; cpu.pc=cpu.rets
        elif cpu.pc==syms['rtc_update']:
            applied.append(cpu.mem.read(cpu.R[0],9)); cpu.R[0]=0; cpu.pc=cpu.rets
        else: cpu.step()
    for _ in range(500):
        if cpu.pc==sim.RETURN: break
        step()
    else: raise AssertionError(name+' receive did not terminate')
    assert cpu.sp==sp and not applied,name
    flag=int.from_bytes(cpu.mem.read(0x16818,4),'little')
    status=int.from_bytes(cpu.mem.read(0x1681c,4),'little')
    if valid:
        assert len(queued)==1 and flag==1 and status==0,name
        cpu.pc=syms['apply_time']; cpu.rets=sim.RETURN; cpu.R[0]=queued[0][2]
        for _ in range(100):
            if cpu.pc==sim.RETURN: break
            step()
        assert applied==[b'\x00\x00'+data[6:13]] and cpu.sp==sp,name
        assert cpu.mem.read(0x16818,8)==b'\x00'*8,name
    elif queue_error:
        assert len(queued)==1 and flag==0 and status==3,name
    elif busy: assert not queued and flag==1,name
    else: assert not queued and status==3,name
    tests.append({'case':name,'result':'passed'})
case('valid_set_is_deferred_then_applied',packet(),valid=True)
case('valid_leap_day_2028',packet(year=2028,month=2,day=29),valid=True)
case('invalid_leap_day_2027',packet(year=2027,month=2,day=29))
case('invalid_april_31',packet(month=4,day=31))
case('invalid_year_2100',packet(year=2100))
case('invalid_month_zero',packet(month=0))
case('invalid_day_zero',packet(day=0))
case('invalid_hour_24',packet(hour=24))
case('invalid_minute_60',packet(minute=60))
case('invalid_second_60',packet(second=60))
case('bad_magic',b'FAIL'+packet()[4:])
case('short_transfer',packet()[:8])
case('queue_error_is_reported',packet(),queue_error=True)
case('busy_request_does_not_overwrite_buffer',packet(),busy=True)
Path('build/sync-validation.json').write_text(json.dumps({'scope':'PI32v2 simulator; firmware APIs mocked','cases':tests},indent=2))
print('Passed',len(tests),'GET/SET/control-transfer tests')

from mivo_m82.bundle import FirmwareBundle
from jltech.cipher import jl_sfc_cipher
bundle = FirmwareBundle()
sector = next(s for s in bundle.sectors if s.offset == 0x5c000)
scratch = bytearray(0x5d000)
scratch[0x5c000:0x5d000] = sector.data
jl_sfc_cipher(scratch, 0x5c000, 4096, 0x2000, 0x77a)
compiled = Path('build/usb_clock.bin').read_bytes()
if scratch[0x5c9c6:0x5c9c6+len(compiled)] != compiled:
    raise RuntimeError('Published binary does not match assembled source')
print('Published firmware code matches assembled source byte for byte')
