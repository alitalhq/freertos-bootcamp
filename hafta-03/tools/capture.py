"""(Eğitmenin Hafta 3 paketindeki tools/capture.py; değiştirilmeden alındı.)
Capture real Week 3 serial results and a verified SystemView RAM snapshot.
Example: python tools/capture.py --port COM4 --variant A --load BURST
"""
import argparse,csv,hashlib,json,time
from pathlib import Path
import serial

def fnv(data):
    h=2166136261
    for b in data:h=((h^b)*16777619)&0xffffffff
    return h

def capture(port,variant,load,out,trace=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    lines=[]
    with serial.Serial(port,230400,timeout=.2) as ser:
        ser.reset_input_buffer()
        def send(s):ser.write((s+'\n').encode());ser.flush()
        def until(prefix,seconds=15):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                data=ser.readline()
                if not data:continue
                s=data.decode('ascii',errors='strict').strip();lines.append(s)
                if s.startswith('#ERROR'):raise RuntimeError(s)
                if s.startswith(prefix):return s.split(',')
            raise TimeoutError(f'No {prefix} from {port}; reset board and retry')
        send('HELLO');hello=until('#HELLO,')
        if hello[1:3]!=['WEEK3','1']:raise ValueError('Firmware mismatch')
        send('TRACE ON' if trace else 'TRACE OFF');until('#ACK,')
        send(f'RUN {variant} {load}');start=until('#RUN,');until('#END,')
        result=next(s.split(',') for s in lines if s.startswith('#RESULT,'))
        rows=[list(map(int,s.split(',')[1:])) for s in lines if s.startswith('#ROW,')]
        attempted,accepted,failed,consumed=map(int,result[4:8])
        assert len(rows)==attempted==44 and accepted+failed==44 and accepted==consumed
        assert len({r[0] for r in rows})==44 and sum(r[1] for r in rows)==accepted and sum(r[2] for r in rows)==consumed
        assert all(r[1]==r[2] for r in rows)
        stem=f'{variant}_{load}_trace{int(trace)}_run{start[1]}_{time.time_ns()}'
        meta={'source':'hardware_serial','port':port,'variant':variant,'load':load,'run_id':int(start[1]),'trace_enabled':trace,
              'attempted':attempted,'accepted':accepted,'failed':failed,'consumed':consumed,'result':result,'trace':None}
        if trace:
            send('TRACE');hdr=until('#TRACE,');until('#TRACE_END,')
            data=bytearray()
            for line in lines:
                if line.startswith('#HEX,'):
                    _,offset,chunk=line.split(',');assert int(offset)==len(data);data.extend(bytes.fromhex(chunk))
            assert int(hdr[1])==int(start[1]) and len(data)==int(hdr[2]) and fnv(data)==int(hdr[3],16)
            (out/(stem+'.SVDat')).write_bytes(data)
            meta['trace']={'bytes':len(data),'fnv1a':hdr[3],'drops':int(hdr[4]),'stop_reason':int(hdr[5]),'sha256':hashlib.sha256(data).hexdigest()}
        (out/(stem+'.txt')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
        with (out/(stem+'.csv')).open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['id','accepted','received','generated_us','send_call_us','generation_to_receive_us'])
            for r in rows:w.writerow(r[:5]+[r[5] if r[2] else ''])
        good=[r[5] for r in rows if r[2]]
        meta['max_latency_us']=max(good,default=0);meta['max_send_us']=max(r[4] for r in rows)
        meta['stack_words']=next(s.split(',')[1:] for s in lines if s.startswith('#STACK,'))
        meta['rx_errors_drops']=next(s.split(',')[1:] for s in lines if s.startswith('#RX,'))
        elf=Path(__file__).resolve().parents[1]/'firmware/build/bootcamp.elf'
        if elf.exists():meta['local_elf_sha256']=hashlib.sha256(elf.read_bytes()).hexdigest()
        (out/(stem+'.json')).write_text(json.dumps(meta,indent=2),encoding='utf-8')
        return meta

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--variant',choices=['A','B','C'],default='A');p.add_argument('--load',choices=['NORMAL','BURST'],default='NORMAL');p.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'measurements/hardware'));p.add_argument('--no-trace',action='store_true');a=p.parse_args()
    print(json.dumps(capture(a.port,a.variant,a.load,a.output,not a.no_trace),indent=2))
