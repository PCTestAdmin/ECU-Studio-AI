"""Generate synthetic, fictional data for safe GUI evaluation; NO real ECU firmware."""
from pathlib import Path
import csv
import random
import struct


def main():
    target=Path(__file__).resolve().parent
    rng=random.Random(94)
    data=bytearray(rng.randbytes(32768))
    # Smooth synthetic pressure-like matrix (not a real ECU boost map).
    for r in range(16):
        for c in range(16):
            v=900 + 65*r + 31*c + (r*c)//6
            struct.pack_into(">H",data,0x1000+2*(r*16+c),v)
    # Smooth synthetic percentage-like matrix, also not a real EGR map.
    for r in range(16):
        for c in range(16):
            v=10 + 2*r + 3*c
            struct.pack_into(">H",data,0x2000+2*(r*16+c),v)
    (target/"demo_synthetic.bin").write_bytes(data)
    with (target/"demo_definitions.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f)
        w.writerow(["name","offset","rows","cols","dtype","endian","factor","bias","unit","kind","notes"])
        w.writerow(["SYNTHETIC Boost demo","0x1000",16,16,"u16","big",1,0,"arbitrary","Boost","Künstliche Testmatrix. Kein Fahrzeugbezug."])
        w.writerow(["SYNTHETIC AGR demo","0x2000",16,16,"u16","big",1,0,"arbitrary","AGR","Künstliche Testmatrix. Kein Fahrzeugbezug."])
    print("Generiert:",target/"demo_synthetic.bin",target/"demo_definitions.csv")


if __name__=="__main__": main()
