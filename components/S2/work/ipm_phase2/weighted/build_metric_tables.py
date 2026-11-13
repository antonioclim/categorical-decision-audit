"""Certify floor(S*a/log2(r+1)) by exact rational logarithm enclosures.

For z=(x-1)/(x+1), log(x)=2*sum(z**(2k+1)/(2k+1), k>=0).
After N terms the positive remainder is at most
2*z**(2N+1)/((2N+1)*(1-z*z)).  All arithmetic below is rational.
Powers of two use the exact integer logarithm, including floor boundaries.
"""
from fractions import Fraction
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

SCALES = (10_000, 1_000_000, 100_000_000)

@lru_cache(None)
def log_bounds(x, n):
    z = Fraction(x-1, x+1)
    term = z
    total = Fraction(0)
    for k in range(n):
        total += term / (2*k+1)
        term *= z*z
    return 2*total, 2*total + 2*term / ((2*n+1)*(1-z*z))

def certify(scale, gain, rank):
    x = rank+1
    if gain == 0:
        return 0, {'method':'zero gain'}
    if x & (x-1) == 0:
        log2 = x.bit_length()-1
        return scale*gain//log2, {'method':'exact power of two', 'log2':log2}
    for n in (32,64,128,256,512):
        a,b = log_bounds(2,n)
        c,d = log_bounds(x,n)
        lower,upper = scale*gain*a/d, scale*gain*b/c
        lo,hi = lower.numerator//lower.denominator, upper.numerator//upper.denominator
        if lo == hi:
            return lo, {'method':'rational logarithm enclosure','terms':n,
                        'floor_lower':lo,'floor_upper':hi}
    raise ArithmeticError('Could not certify floor within the fixed term budget')

def build():
    tables = {}
    evidence = []
    for scale in SCALES:
        table=[]
        for rank in range(1,11):
            row=[]
            for gain in range(4):
                value,proof = certify(scale,gain,rank)
                row.append(value)
                evidence.append({'scale':scale,'rank':rank,'gain':gain,'value':value,**proof})
            table.append(row)
        tables[str(scale)]=table
    return tables,evidence

if __name__ == '__main__':
    here=Path(__file__).resolve().parent
    tables,evidence=build()
    raw=(json.dumps(tables,sort_keys=True,separators=(',',':'))+'\n').encode()
    (here/'metric_tables.json').write_bytes(raw)
    out={'status':'certified','metric':'quantised_log_discount_floor_gain_v1',
         'table_file_sha256':sha256(raw).hexdigest(),'nonzero_entries':90,
         'scope':'Exact integer quantisation; not exact real-valued DCG or nDCG',
         'entries':evidence}
    (here/'metric_table_certification.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='entries'},indent=2))
