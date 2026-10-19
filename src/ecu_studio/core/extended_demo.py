"""Multi-family synthetic calibration examples incl. an ASAP2 A2L linking exercise.

All data is fictional and unsuitable for a vehicle/ECU.
"""
from __future__ import annotations
from pathlib import Path
import random
import struct
from .a2l import parse_a2l

# Name, description, shape, width, zero-based file offset.
DEMO_MAPS = [
    ('BOOST_REQUEST','Boost pressure target',16,16,'UWORD',0x1000),
    ('EGR_RATE','AGR EGR rate reference',16,16,'UWORD',0x1500),
    ('TORQUE_MAX','Torque limiter',16,16,'UWORD',0x2000),
    ('INJECTION_QUANTITY','Injection duration example',16,16,'UWORD',0x2800),
    ('IGNITION_ADVANCE','Ignition spark angle example',16,16,'SWORD',0x3000),
    ('LAMBDA_TARGET','Lambda air-fuel target',16,16,'UWORD',0x3800),
    ('WASTEGATE_REQUEST','Wastegate turbo control',16,16,'UWORD',0x4000),
    ('IDLE_SPEED_REQUEST','Idle speed',1,16,'UWORD',0x4800),
    ('THERMAL_PROTECTION','Temperature protection',16,16,'UWORD',0x5000),
    ('RAIL_PRESSURE_REQUEST','Rail pressure request',16,16,'UWORD',0x5800),
    ('DRIVER_WISH_PEDAL','Driver wish pedal position',16,16,'UWORD',0x6000),
    ('SMOKE_LIMITER','Smoke limiter',16,16,'UWORD',0x6800),
    ('NOX_MODEL','NOx model (fictional)',1,16,'UBYTE',0x7000),
    ('DIAGNOSTIC_THRESHOLD','Diagnostic threshold',1,1,'ULONG',0x7200),
]


def generate_extended_demo(folder: str) -> tuple[Path, Path]:
    target=Path(folder)
    target.mkdir(parents=True,exist_ok=True)
    data=bytearray(random.Random(420).randbytes(0x9000))
    a2l=['ASAP2_VERSION 1 71','/begin PROJECT SYNTHETIC "ECU Studio training set"',
         ' /begin MODULE ECU "Fictional demo only"',
         '  /begin MOD_COMMON "Demo byte order"',
         '   BYTE_ORDER MSB_FIRST',
         '  /end MOD_COMMON']
    for name, dtype in [('RL_UBYTE','UBYTE'),('RL_UWORD','UWORD'),('RL_SWORD','SWORD'),('RL_ULONG','ULONG')]:
        a2l += [f'  /begin RECORD_LAYOUT {name}',f'   FNC_VALUES 1 {dtype} ROW_DIR DIRECT',
                 '  /end RECORD_LAYOUT']
    types={'UWORD':('>H',0,65535),'SWORD':('>h',-32768,32767),
           'ULONG':('>I',0,4294967295),'UBYTE':('>B',0,255)}
    for index,(name,desc,rows,cols,dtype,offset) in enumerate(DEMO_MAPS):
        format_,lower,upper=types[dtype]
        for r in range(rows):
            for c in range(cols):
                candidate = (25 + index*9 + r*4 + c*3 + r*c//8)
                if dtype=='SWORD':candidate -= 170
                if dtype=='ULONG':candidate *= 100000
                if dtype=='UBYTE':candidate %= 255
                value=max(lower,min(upper,candidate))
                struct.pack_into(format_,data,offset+(r*cols+c)*struct.calcsize(format_),value)
        kind='VALUE' if rows==cols==1 else 'CURVE' if rows==1 else 'MAP'
        a2l += [f'  /begin CHARACTERISTIC {name} "{desc}" {kind} 0x{0x800000+offset:X} RL_{dtype} 0 NO_COMPU_METHOD 0 65535',
                f'   MATRIX_DIM {cols} {rows} 1']
        if rows>1:
            a2l += ['   /begin AXIS_DESCR FIX_AXIS RPM NO_COMPU_METHOD 16 0 16000',
                    '    FIX_AXIS_PAR_DIST 0 1000 16','   /end AXIS_DESCR']
        if cols>1:
            a2l += [f'   /begin AXIS_DESCR FIX_AXIS LOAD NO_COMPU_METHOD {cols} 0 200',
                    f'    FIX_AXIS_PAR_DIST 0 10 {cols}','   /end AXIS_DESCR']
        a2l.append('  /end CHARACTERISTIC')
    a2l.extend([' /end MODULE','/end PROJECT'])
    image_path=target/'demo_multi_map.bin'
    label_path=target/'demo_multi_map.a2l'
    image_path.write_bytes(data)
    label_path.write_text('\n'.join(a2l)+'\n',encoding='utf-8')
    return image_path,label_path
