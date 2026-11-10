// USB RTC service. Apply SET requests through app_core's callback queue.
.text
.globl usb_probe
usb_probe:
    if (r1 == -1) goto fallback
    r2 = b[r1+0] (u)
    r2 = r2 & 0x60
    if (r2 == 0) goto standard
    if (r2 != 32) goto fallback
    r2 = b[r1+1] (u)
    if (r2 == 9) goto set_request
    if (r2 != 1) goto fallback
    r2 = h[r1+2] (u)
    if (r2 != 0x0300) goto fallback
    r2 = h[r1+6] (u)
    if (r2 < 16) goto fallback
    [--sp] = {rets, r5, r4}
    sp += -16
    r5_r4 = r1_r0
    r0 = 0
    [sp] = r0
    [sp+4] = r0
    [sp+8] = r0
    [sp+12] = r0
    r0 = 86128
    r0 = [r0+204]
    if (r0 == 0) goto rtc_absent
    r1 = 19
    r2 = sp + 4
    call dev_ioctl
    r1 = 0x16808
    r0 = [r1+20]
    r1 = [r1+16]
    if (r1 == 0) goto rtc_done
    r0 = 2
    goto rtc_done
rtc_absent:
    r0 = 1
rtc_done:
    b[sp+5] = r0
    r0 = 2
    b[sp+4] = r0
    r0 = 0x5432384d
    [sp] = r0
    r1_r0 = r5_r4
    r2 = sp + 0
    r3 = 16
    call usb_payload
    r0 = 0
    sp += 16
    {pc, r5, r4} = [sp++]
set_request:
    r2 = h[r1+2] (u)
    if (r2 != 0x0300) goto fallback
    r2 = h[r1+6] (u)
    if (r2 != 16) goto fallback
    [--sp] = rets
    r1 = receive_time
    call usb_set_recv
    r0 = 0
    pc = [sp++]
standard:
    r2 = b[r1+1] (u)
    if (r2 != 6) goto fallback
    r2 = h[r1+2] (u)
    r2 = r2 >> 8
    if (r2 == 34) goto report_descriptor
    if (r2 != 33) goto fallback
    [--sp] = rets
    r2 = 31744877
    r3 = 9
    call usb_payload
    r1 = report_end-report
    b[r0+7] = r1
    r1 = 0
    b[r0+8] = r1
    r0 = 0
    pc = [sp++]
report_descriptor:
    [--sp] = {rets, r5, r4}
    r5_r4 = r1_r0
    call hid_endpoint_init
    r1_r0 = r5_r4
    r2 = report
    r3 = report_end-report
    call usb_payload
    r0 = 0
    {pc, r5, r4} = [sp++]
fallback:
    [--sp] = {rets, r6-r4}
    r5_r4 = r1_r0
    goto resume_hid
.globl receive_time
receive_time:
    [--sp] = {rets, r6-r4}
    sp += -32
    r0 = 0
    r1 = sp + 0
    r2 = 16
    call usb_read_ep0
    r4 = 0x16808
    r0 = [sp]
    r1 = 0x5432384d
    if (r0 != r1) goto bad_packet
    r0 = h[sp+4] (u)
    if (r0 != 257) goto bad_packet
    r0 = [r4+16]
    if (r0 != 0) goto receive_done
    r0 = h[sp+6] (u)
    r0 += -2000
    if (r0 > 99) goto bad_packet
    r6 = r0
    r0 = b[sp+8] (u)
    r0 += -1
    if (r0 > 11) goto bad_packet
    r1 = month_days
    r1 = b[r1+r0] (u)
    if (r0 != 1) goto check_day
    r6 = r6 & 3
    if (r6 != 0) goto check_day
    r1 += 1
check_day:
    r0 = b[sp+9] (u)
    if (r0 == 0) goto bad_packet
    if (r0 > r1) goto bad_packet
    r0 = b[sp+10] (u)
    if (r0 > 23) goto bad_packet
    r0 = b[sp+11] (u)
    if (r0 > 59) goto bad_packet
    r0 = b[sp+12] (u)
    if (r0 > 59) goto bad_packet
    r0 = 86128
    r0 = [r0+204]
    if (r0 == 0) goto bad_packet
    r0 = [sp]
    [r4+0] = r0
    r0 = [sp+4]
    [r4+4] = r0
    r0 = [sp+8]
    [r4+8] = r0
    r0 = [sp+12]
    [r4+12] = r0
    r0 = 0
    h[r4+4] = r0
    [r4+20] = r0
    r0 = 1
    [r4+16] = r0
    r0 = apply_time
    [sp+16] = r0
    r0 = 1
    [sp+20] = r0
    r0 = r4 + 4
    [sp+24] = r0
    r0 = 0x1e460b3
    r1 = 0x300000
    r2 = 3
    r3 = sp + 16
    r6 = 0x1716a
    call r6
    if (r0 == 0) goto receive_done
    r0 = 0
    [r4+16] = r0
bad_packet:
    r0 = 3
    [r4+20] = r0
receive_done:
    r0 = 0
    sp += 32
    {pc, r6-r4} = [sp++]
.globl apply_time
apply_time:
    [--sp] = rets
    call rtc_update
    r0 = 0x16808
    r1 = 0
    [r0+16] = r1
    [r0+20] = r1
    pc = [sp++]
month_days:
    .byte 31,28,31,30,31,30,31,31,30,31,30,31
.balign 2
report:
    .incbin "build/hid-prefix.bin"
    .byte 0x06,0x00,0xff,0x09,0x01,0x15,0x00,0x26,0xff,0x00,0x75,0x08,0x95,0x10,0xb1,0x02,0xc0
report_end:
