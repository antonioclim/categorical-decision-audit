"""Export the native Draw figures through LibreOffice and render 600 dpi PNGs."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    office=shutil.which('soffice') or shutil.which('libreoffice')
    poppler=shutil.which('pdftoppm')
    if not office or not poppler:
        raise RuntimeError('LibreOffice and pdftoppm must be installed and available on PATH.')
    files=sorted(ROOT.glob('Figure_*.odg'))
    if len(files)!=3:raise RuntimeError('Build the three ODG figures before exporting.')
    with tempfile.TemporaryDirectory(prefix='paperm-figure-profile-') as profile:
        cmd=[office,'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--norestore',
             '--convert-to','pdf:draw_pdf_Export','--outdir',str(ROOT),*[str(p)for p in files]]
        result=subprocess.run(cmd,capture_output=True,text=True,check=True)
    for source in files:
        pdf=source.with_suffix('.pdf')
        if not pdf.is_file():raise RuntimeError('LibreOffice did not create '+str(pdf))
        subprocess.run([poppler,'-png','-r','600','-singlefile',str(pdf),str(source.with_suffix(''))],check=True)
    print(json.dumps({'files':[p.name for p in files],'exporter':office,
        'version':subprocess.run([office,'--version'],capture_output=True,text=True,check=True).stdout.strip(),
        'png_dpi':600,'stdout':result.stdout,'stderr':result.stderr},indent=2))

if __name__=='__main__':main()
