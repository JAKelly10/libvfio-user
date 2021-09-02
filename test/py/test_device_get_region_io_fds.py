from libvfio_user import *
import ctypes as c
import errno
import tempfile
import os
import struct

libc = c.cdll.LoadLibrary("libc.so.6")
def eventfd(init_val, flags):
    return libc.eventfd(init_val, flags)


ctx = None
sock = None

def test_device_get_region_io_fds_setup():
    global ctx, sock

    ctx = vfu_create_ctx(flags=LIBVFIO_USER_FLAG_ATTACH_NB)
    assert ctx != None

    ret = vfu_setup_region(ctx, index=VFU_PCI_DEV_BAR1_REGION_IDX, size=4096,
                           flags=(VFU_REGION_FLAG_RW | VFU_REGION_FLAG_MEM))
    assert ret == 0

    f = tempfile.TemporaryFile()
    f.truncate(65536)

    mmap_areas = [ (0x2000, 0x1000), (0x4000, 0x2000) ]

    ret = vfu_setup_region(ctx, index=VFU_PCI_DEV_BAR2_REGION_IDX, size=0x8000,
                           flags=(VFU_REGION_FLAG_RW | VFU_REGION_FLAG_MEM),
                           mmap_areas=mmap_areas, fd=f.fileno(), offset=0x8000)
    assert ret == 0

    f = tempfile.TemporaryFile()
    f.truncate(0x2000)

    mmap_areas = [ (0x1000, 0x1000) ]

    ret = vfu_setup_region(ctx, index=VFU_PCI_DEV_MIGR_REGION_IDX, size=0x2000,
                           flags=VFU_REGION_FLAG_RW, mmap_areas=mmap_areas,
                           fd=f.fileno())
    assert ret == 0

    ret = vfu_realize_ctx(ctx)
    assert ret == 0

    sock = connect_client(ctx)

    for i in range(0,6):
        tmp = eventfd(0,0)
        assert vfu_create_ioeventfd(ctx, i * 8, 8, tmp, 0, VFU_PCI_DEV_BAR2_REGION_IDX) != -1

def test_device_get_region_io_fds_bad_flags():

    payload = region_io_fds_request(argsz = 16+40*5, flags = 1, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 0)

    msg(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=errno.EINVAL)

def test_device_get_region_io_fds_bad_count():

    payload = region_io_fds_request(argsz = 16+40*5, flags = 0, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 1)

    msg(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=errno.EINVAL)

def test_device_get_region_io_fds_buffer_to_small():

    payload = region_io_fds_request(argsz = 15, flags = 0, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 1)

    msg(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=errno.EINVAL)

def test_device_get_region_io_fds_buffer_to_large():

    payload = region_io_fds_request(argsz = SERVER_MAX_DATA_XFER_SIZE+1, flags = 0, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 1)

    msg(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=errno.EINVAL)


def test_device_get_region_io_fds_fds_read_write():

    payload = region_io_fds_request(argsz = 16+40*4, flags = 0, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 0)

    newfds, ret = msg_fd(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=0)

    reply, ret = region_io_fds_reply.pop_from_buffer(ret)
    ioevent, ret = sub_region_ioeventfd.pop_from_buffer(ret)

    print(newfds)
    for i in range(0,4):
        os.write(newfds[i], c.c_ulonglong(10))
        out = os.read(newfds[i], 8)
        [out] = struct.unpack("@Q",out)
        assert out  == 10

def test_device_get_region_io_fds_full():

    payload = region_io_fds_request(argsz = 16+(40*6), flags = 0, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 0)

    newfds, ret = msg_fd(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=0)

    reply, ret = region_io_fds_reply.pop_from_buffer(ret)
    ioevents = []
    for i in range(0, reply.count):
        ioevent, ret = sub_region_ioeventfd.pop_from_buffer(ret)
        ioevents.append(ioevent)
        os.write(newfds[ioevent.fd_index], c.c_ulonglong(1))

    print(newfds, [i.fd_index for i in ioevents])

    for i in range(0, reply.count):
        out = os.read(newfds[ioevents[i].fd_index], ioevent.size)
        [out] = struct.unpack("@Q",out)
        assert out  == 1
        assert ioevents[i].size == 8
        assert ioevents[i].offset == 40 - (8 * i)

def test_device_get_region_io_fds_fds_read_write_nothing():

    payload = region_io_fds_request(argsz = 16, flags = 0, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 0)

    newfds, ret = msg_fd(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=0)

    reply, ret = region_io_fds_reply.pop_from_buffer(ret)
    assert reply.argsz == 16

def test_device_get_region_io_fds_fds_read_write_dupe_fd():

    t = eventfd(0,0)
    assert vfu_create_ioeventfd(ctx, 6 * 8, 8, t, 0, VFU_PCI_DEV_BAR2_REGION_IDX) != -1
    assert vfu_create_ioeventfd(ctx, 7 * 8, 8, t, 0, VFU_PCI_DEV_BAR2_REGION_IDX) != -1


    payload = region_io_fds_request(argsz = 16+(40*8), flags = 0, index = VFU_PCI_DEV_BAR2_REGION_IDX, count = 0)

    newfds, ret = msg_fd(ctx, sock, VFIO_USER_DEVICE_GET_REGION_IO_FDS, payload, expect=0)
    reply, ret = region_io_fds_reply.pop_from_buffer(ret)

    assert reply.count == 8
    assert reply.argsz == 16+(40*8)

    ioevents = []
    for i in range(0, reply.count):
        ioevent, ret = sub_region_ioeventfd.pop_from_buffer(ret)
        ioevents.append(ioevent)

    for i in range(2, 8):
        os.write(newfds[ioevents[i].fd_index], c.c_ulonglong(1))

    print(newfds, [i.fd_index for i in ioevents])

    for i in range(2, 8):
        out = os.read(newfds[ioevents[i].fd_index], ioevent.size)
        [out] = struct.unpack("@Q",out)
        assert out  == 1
        assert ioevents[i].size == 8
        assert ioevents[i].offset == 56 - (8 * i)


    assert ioevents[0].fd_index == ioevents[1].fd_index
    assert ioevents[0].offset != ioevents[1].offset

    os.write(newfds[ioevents[0].fd_index], c.c_ulonglong(1))
    out = os.read(newfds[ioevents[1].fd_index], ioevent.size)
    [out] = struct.unpack("@Q",out)
    assert out == 1




def test_device_setup_ioeventfd():
    assert create_ioeventfd(ctx, 0, 0, VFU_PCI_DEV_BAR1_REGION_IDX) != -1
    assert create_ioeventfd(ctx, 8, 0, VFU_PCI_DEV_BAR1_REGION_IDX) != -1
    assert create_ioeventfd(ctx, 16, 0, VFU_PCI_DEV_BAR1_REGION_IDX) != -1

    assert delete_ioeventfd(ctx, VFU_PCI_DEV_BAR1_REGION_IDX, 1) == 0
    assert delete_ioeventfd(ctx, VFU_PCI_DEV_BAR1_REGION_IDX, 1) == 0
    assert delete_ioeventfd(ctx, VFU_PCI_DEV_BAR1_REGION_IDX, 0) == 0

def test_device_get_region_info_cleanup():
    vfu_destroy_ctx(ctx)
