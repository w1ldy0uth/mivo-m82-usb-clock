ENTRY(usb_probe)
dev_ioctl = 0x01e0cf6e;
usb_payload = 0x01e32952;
hid_endpoint_init = 0x01e32cee;
resume_hid = 0x01e32d2e;
usb_set_recv = 0x01e32d16;
usb_read_ep0 = 0x01e32de4;
rtc_update = 0x01e3f732;
SECTIONS { .text 0x01e5a9c6 : { *(.text) } }
