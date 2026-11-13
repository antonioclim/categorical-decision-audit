"""Audit native ODG objects and test edits through LibreOffice save/reopen/export.

Edits are made through ODF XML, not GUI automation. Each edited copy is then
opened and saved as ODG by LibreOffice, reopened and exported to PDF. Clean
research figures remain unchanged. This is a format/roundtrip test, not a
claim that all interactive editor operations have been exercised.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from xml.etree import ElementTree as E
from collections import Counter
from hashlib import sha256
import json
import shutil
import subprocess
import tempfile
import sys

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/editability'
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_figures import NS,q

def read(path):
    with ZipFile(path) as z:
        assert z.testzip() is None
        assert z.read('mimetype')==b'application/vnd.oasis.opendocument.graphics'
        assert z.infolist()[0].filename=='mimetype' and z.infolist()[0].compress_type==ZIP_STORED
        entries={i.filename:z.read(i.filename)for i in z.infolist()}
    return entries,E.fromstring(entries['content.xml'])

def items(root):return list(root.find('.//'+q('draw:page')))
def texts(root):return [''.join(p.itertext())for p in root.iter(q('text:p'))]
def named(root,name):return next(e for e in items(root)if e.get(q('draw:name'))==name)
def save(path,entries,root):
    entries['content.xml']=E.tostring(root,encoding='utf-8',xml_declaration=True)
    with ZipFile(path,'w')as z:
        z.writestr('mimetype',entries.pop('mimetype'),compress_type=ZIP_STORED)
        for name,data in entries.items():z.writestr(name,data,compress_type=ZIP_DEFLATED)

def office_convert(office,sources,folder,filter):
    folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='paperm-editability-profile-')as profile:
        cmd=[office,'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--norestore',
             '--convert-to',filter,'--outdir',str(folder),*[str(p)for p in sources]]
        result=subprocess.run(cmd,capture_output=True,text=True,check=True)
    return {'filter':filter,'stdout':result.stdout.replace(str(ROOT) + '/', ''),'stderr':result.stderr.replace(str(ROOT) + '/', ''),'exit_code':result.returncode}

def main():
    office=shutil.which('soffice')or shutil.which('libreoffice')
    if not office:raise RuntimeError('LibreOffice is required for native roundtrip checks.')
    edited=QA/'edited_input';saved=QA/'native_saved';pdfs=QA/'reopened_pdf'
    edited.mkdir(parents=True,exist_ok=True)
    checks=[]
    for source in sorted(ROOT.glob('Figure_*.odg')):
        entries,root=read(source);objects=items(root)
        names=[e.get(q('draw:name'))for e in objects]
        assert len(names)==len(set(names)) and all(names)
        assert not list(root.iter(q('draw:image')))
        assert not list(root.iter(q('draw:object')))
        assert not list(root.iter(q('draw:object-ole')))
        counts=Counter(e.tag.split('}')[-1]for e in objects)
        assert counts['frame']>=24 and counts['rect']>=10
        text_before=texts(root)
        title=next(e for e in objects if e.tag==q('draw:frame'))
        p=next(title.iter(q('text:p')));p.text='EDIT TEST context'
        axis=next((e for e in objects if 'axis_title' in e.get(q('draw:name'),'')),None)
        if axis is None:axis=objects[2]
        ap=next(axis.iter(q('text:p')));ap.text='EDIT TEST axis'
        shape=next(e for e in objects if e.tag==q('draw:rect') and
                   ('_bar' in e.get(q('draw:name'),'') or 'joint_count_cell' in e.get(q('draw:name'),'')))
        old=shape.get(q('svg:width'));new=f'{float(old[:-2])+.2:.4f}cm'
        shape.set(q('svg:width'),new)
        line=next((e for e in objects if 'editable_axis' in e.get(q('draw:name'),'')),None)
        if line is not None:
            before=line.get(q('svg:x2'));line.set(q('svg:x2'),f'{float(before[:-2])-.2:.4f}cm')
        else:before=None
        dest=edited/source.name;save(dest,entries,root)
        checks.append({'file':source.name,'source_sha256':sha256(source.read_bytes()).hexdigest(),
            'object_counts':dict(counts),'unique_native_objects':len(objects),'raster_objects':0,'embedded_foreign_objects':0,
            'text_objects':counts['frame'],'context_text_object':title.get(q('draw:name')),
            'axis_text_object':axis.get(q('draw:name')),'geometry_object':shape.get(q('draw:name')),
            'old_width_cm':float(old[:-2]),'edited_width_cm':float(new[:-2]),
            'axis_line_object':line.get(q('draw:name'))if line is not None else None,
            'edited_axis_x2_cm':float(line.get(q('svg:x2'))[:-2])if line is not None else None,
            'original_text_paragraphs':len(text_before)})
    logs=[office_convert(office,sorted(edited.glob('*.odg')),saved,'odg:draw8'),
          office_convert(office,sorted(saved.glob('*.odg')),pdfs,'pdf:draw_pdf_Export')]
    for row in checks:
        output=saved/row['file'];_,root=read(output)
        assert 'EDIT TEST context' in texts(root) and 'EDIT TEST axis' in texts(root)
        shape=named(root,row['geometry_object'])
        assert abs(float(shape.get(q('svg:width'))[:-2])-row['edited_width_cm'])<.001
        if row['axis_line_object']:
            axis_line=named(root,row['axis_line_object'])
            assert abs(float(axis_line.get(q('svg:x2'))[:-2])-row['edited_axis_x2_cm'])<.001
        assert len(items(root))==row['unique_native_objects']
        assert not list(root.iter(q('draw:image')))
        pdf=pdfs/(Path(row['file']).stem+'.pdf');assert pdf.is_file()
        row.update({'native_save_reopen_export':'passed','saved_sha256':sha256(output.read_bytes()).hexdigest(),
            'pdf_sha256':sha256(pdf.read_bytes()).hexdigest(),'clean_source_unchanged':sha256((ROOT/row['file']).read_bytes()).hexdigest()==row['source_sha256']})
    result={'status':'passed','method':__doc__,'office_version':subprocess.run([office,'--version'],capture_output=True,text=True,check=True).stdout.strip(),
        'checks':checks,'native_conversion_logs':logs}
    (ROOT/'qa/editability_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='native_conversion_logs'},indent=2))

if __name__=='__main__':main()
