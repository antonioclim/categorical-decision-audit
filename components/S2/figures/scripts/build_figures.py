"""Build three native editable OpenDocument Draw figures from fixed source data.

Python standard library only. Every visible primitive is an individual Draw
shape or text box. PDF/PNG export is performed separately by LibreOffice.
"""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED
from xml.etree import ElementTree as E
from collections import Counter
import json

ROOT = Path(__file__).resolve().parents[1]
NS = {
 'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
 'style':'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
 'text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
 'draw':'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
 'fo':'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
 'svg':'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
 'dc':'http://purl.org/dc/elements/1.1/',
 'meta':'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
 'manifest':'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0',
}
for prefix,uri in NS.items(): E.register_namespace(prefix,uri)
def q(s):
 a,b=s.split(':',1);return '{'+NS[a]+'}'+b
def el(parent,tag,attrs=None,text=None):
 n=E.SubElement(parent,q(tag),{q(k):str(v)for k,v in (attrs or {}).items()})
 if text is not None:n.text=str(text)
 return n
def xml(root):return E.tostring(root,encoding='utf-8',xml_declaration=True)
def cm(x):return f'{x:.4f}cm'

INK='#17252c'; BLUE='#245a73'; PALE='#eaf0f3'; GREY='#a5a5a5'; RULE='#b8c2c8'; ORANGE='#bd6736'; WARM='#fbefe6'

class Figure:
 def __init__(self,name,title,height):
  self.name=name;self.title=title;self.height=height-.7;self.objects=[];self.styles={};self.ps={};self.counter=Counter()
  self.root=E.Element(q('office:document-content'),{q('office:version'):'1.2'})
  f=el(self.root,'office:font-face-decls');el(f,'style:font-face',{'style:name':'Liberation Sans','svg:font-family':'Liberation Sans','style:font-family-generic':'swiss','style:font-pitch':'variable'})
  self.auto=el(self.root,'office:automatic-styles')
  ds=el(self.auto,'style:style',{'style:name':'page','style:family':'drawing-page'})
  el(ds,'style:drawing-page-properties',{'draw:fill':'solid','draw:fill-color':'#ffffff'})
  self.page=el(el(self.root,'office:body'),'office:drawing')
  self.page=el(self.page,'draw:page',{'draw:name':name,'draw:style-name':'page','draw:master-page-name':'Default'})
 def style(self,fill=None,stroke=None,width=.02):
  key=(fill,stroke,width)
  if key in self.styles:return self.styles[key]
  name='g'+str(len(self.styles)+1);self.styles[key]=name
  st=el(self.auto,'style:style',{'style:name':name,'style:family':'graphic'})
  attrs={'draw:fill':'solid'if fill else'none','draw:stroke':'solid'if stroke else'none',
    'fo:padding-left':'0cm','fo:padding-right':'0cm','fo:padding-top':'0cm','fo:padding-bottom':'0cm',
    'draw:textarea-vertical-align':'middle','draw:auto-grow-height':'false','draw:auto-grow-width':'false'}
  if fill:attrs['draw:fill-color']=fill
  if stroke:attrs.update({'svg:stroke-color':stroke,'svg:stroke-width':cm(width)})
  el(st,'style:graphic-properties',attrs);return name
 def paragraph(self,size=10,bold=False,color=INK,align='left'):
  key=(size,bold,color,align)
  if key in self.ps:return self.ps[key]
  name='p'+str(len(self.ps)+1);self.ps[key]=name
  st=el(self.auto,'style:style',{'style:name':name,'style:family':'paragraph'})
  el(st,'style:paragraph-properties',{'fo:text-align':align,'fo:margin-top':'0cm','fo:margin-bottom':'0cm','fo:margin-left':'0cm','fo:margin-right':'0cm','fo:line-height':'100%'})
  el(st,'style:text-properties',{'style:font-name':'Liberation Sans','fo:font-size':str(size)+'pt','fo:font-weight':'bold'if bold else'normal','fo:color':color,'fo:language':'en','fo:country':'GB'})
  return name
 def add(self,kind,name,attrs):
  # Journal captions carry the figure title; remove its 7 mm band.
  attrs = dict(attrs)
  for key in ('svg:y', 'svg:y1', 'svg:y2'):
   if key in attrs:attrs[key]=cm(float(attrs[key][:-2])-.7)
  self.counter[kind]+=1
  name=f'{name}_{self.counter[kind]:03d}'
  n=el(self.page,'draw:'+kind,{'draw:name':name,**attrs});self.objects.append({'name':name,'type':kind,'attributes':attrs})
  return n
 def rect(self,x,y,w,h,fill=None,stroke=None,name='rectangle',width=.02):
  return self.add('rect',name,{'draw:style-name':self.style(fill,stroke,width),'svg:x':cm(x),'svg:y':cm(y),'svg:width':cm(w),'svg:height':cm(h)})
 def line(self,x1,y1,x2,y2,color=RULE,width=.015,name='line'):
  return self.add('line',name,{'draw:style-name':self.style(None,color,width),'svg:x1':cm(x1),'svg:y1':cm(y1),'svg:x2':cm(x2),'svg:y2':cm(y2)})
 def text(self,x,y,w,h,text,size=10,bold=False,color=INK,align='left',name='text'):
  n=self.add('frame',name,{'draw:style-name':self.style(),'svg:x':cm(x),'svg:y':cm(y),'svg:width':cm(w),'svg:height':cm(h)})
  b=el(n,'draw:text-box')
  for line in str(text).split('\n'):el(b,'text:p',{'text:style-name':self.paragraph(size,bold,color,align)},text=line)
  self.objects[-1]['text']=str(text);return n
 def axis(self,x,y,w,maximum,ticks,title):
  self.line(x,y,x+w,y,color=INK,width=.02,name='editable_axis')
  for tick in ticks:
   xx=x+w*tick/maximum;self.line(xx,y,xx,y+.12,color=INK,name='axis_tick')
   self.text(xx-.7,y+.18,1.4,.38,f'{tick:,}',9.5,align='center',name='axis_label')
  self.text(x,y+.68,w,.4,title,10,align='center',name='axis_title')
 def save(self):
  s=E.Element(q('office:document-styles'),{q('office:version'):'1.2'})
  f=el(s,'office:font-face-decls');el(f,'style:font-face',{'style:name':'Liberation Sans','svg:font-family':'Liberation Sans','style:font-family-generic':'swiss'})
  el(s,'office:styles');auto=el(s,'office:automatic-styles')
  pl=el(auto,'style:page-layout',{'style:name':'layout'})
  el(pl,'style:page-layout-properties',{'fo:page-width':'17.8cm','fo:page-height':cm(self.height),'style:print-orientation':'landscape','fo:margin-top':'0cm','fo:margin-bottom':'0cm','fo:margin-left':'0cm','fo:margin-right':'0cm'})
  masters=el(s,'office:master-styles');el(masters,'style:master-page',{'style:name':'Default','style:page-layout-name':'layout'})
  meta=E.Element(q('office:document-meta'),{q('office:version'):'1.2'});m=el(meta,'office:meta')
  el(m,'dc:title',text=self.title);el(m,'dc:description',text='Prepared from recorded analysis outputs. Native editable Draw shapes.')
  el(m,'meta:generator',text='Paper M deterministic native Draw figure builder')
  manifest=E.Element(q('manifest:manifest'),{q('manifest:version'):'1.2'})
  for path,media in [('/','application/vnd.oasis.opendocument.graphics'),('content.xml','text/xml'),('styles.xml','text/xml'),('meta.xml','text/xml')]:
   el(manifest,'manifest:file-entry',{'manifest:full-path':path,'manifest:media-type':media})
  target=ROOT/(self.name+'.odg')
  with ZipFile(target,'w')as z:
   for path,body in [('mimetype',b'application/vnd.oasis.opendocument.graphics'),('content.xml',xml(self.root)),('styles.xml',xml(s)),('meta.xml',xml(meta)),('META-INF/manifest.xml',xml(manifest))]:
    info=ZipInfo(path,date_time=(2026,11,12,0,0,0));info.compress_type=ZIP_STORED if path=='mimetype'else ZIP_DEFLATED;info.external_attr=0o644<<16
    z.writestr(info,body)
  return {'file':target.name,'page_width_cm':17.8,'page_height_cm':self.height,'native_objects':dict(self.counter),'objects':self.objects}

def fig1(d):
 f=Figure('Figure_1_Shared_Completion','Shared completion outcomes for query 2017299',11.4)
 f.text(.45,.95,16.9,.4,'DL22 query 2017299 · flat scores · six unknown grades · 4,096 completions',9.5)
 f.text(4.7,1.6,11.3,.45,'Run omitted by linear graded coding',10,True,align='center')
 labels=d['omitted_labels'];x=5.05;y=2.85;cw=3.75;ch=1.75
 f.text(.45,2.0,3.8,.8,'Run omitted by\nbinary coding',10,True)
 for i,label in enumerate(labels):
  f.text(x+i*cw,2.15,cw,.45,label,10,True,align='center')
  f.text(.45,y+i*ch+.58,4.15,.5,label,10,True,align='right')
  for j in range(3):
   diag=i==j;count=d['matrix'][i][j]
   f.rect(x+j*cw,y+i*ch,cw,ch,BLUE if diag else WARM,RULE,name='joint_count_cell')
   f.text(x+j*cw,y+i*ch+.5,cw,.62,f'{count:,}',15,True,'#ffffff'if diag else INK,'center',name='joint_count')
   label='All-zero point'if [i,j]==d['all_zero_cell'] else 'All-three point'if[i,j]==d['all_three_cell']else''
   if label:f.text(x+j*cw,y+i*ch+1.21,cw,.35,label,9.5,color='#ffffff',align='center',name='constant_point_annotation')
 f.rect(.45,8.65,.32,.32,BLUE,name='agreement_key');f.text(.92,8.59,7.1,.45,'Agreement: 2,500 completions',10)
 f.rect(8.35,8.65,.32,.32,WARM,ORANGE,name='disagreement_key');f.text(8.82,8.59,8.4,.45,'Disagreement: 1,596 completions',10)
 f.text(.45,9.43,16.8,.45,'The omitted run identifies the top-three membership set; RankLLaMA is always included.',9.5)
 f.text(.45,10.12,16.8,.45,'Counts describe completions, not probabilities. Both constant point checks lie on the diagonal.',9.5)
 return f.save()

def fig2(d):
 f=Figure('Figure_2_Discounted_Sensitivity','Point screening under flat and discounted scoring',13.2)
 f.text(.45,.92,16.9,.4,'DL22 naturally incomplete stratum: 70 cases · primary discount scale λ = 10⁶',9.5)
 f.rect(8.0,1.55,.45,.25,GREY,name='flat_legend');f.text(8.62,1.44,2.0,.5,'Flat',9.5)
 f.rect(10.7,1.55,.45,.25,BLUE,name='discount_legend');f.text(11.32,1.44,5.0,.5,'Logarithmic discount',9.5)
 lookup={(r['endpoint'],r['metric'],r['property']):r['count']for r in d['rows']}
 x=5.15;w=11.6
 labels=[('any_change','Possible change'),('strict_change','Strict change'),('all_zero_disagrees','Detected at all-zero')]
 for ep,title,top in [('set','A  Top-three membership',2.1),('prefix','B  Ordered top-three prefix',7.25)]:
  f.text(.45,top,16.9,.5,title,10.5,True)
  for k in [0,10,20,30,40,50,60,70]:f.line(x+w*k/70,top+.8,x+w*k/70,top+3.35,RULE,.01,'gridline')
  for i,(prop,label)in enumerate(labels):
   yy=top+.85+i*.88
   f.text(.45,yy+.13,4.45,.5,label,9.5,align='right')
   for j,metric in enumerate(['Flat','Discount']):
    value=lookup[ep,metric,prop];barwidth=w*value/70;by=yy+j*.32
    f.rect(x,by,barwidth,.24,GREY if metric=='Flat'else BLUE,name=f'{ep}_{prop}_{metric}_bar')
    f.text(x+barwidth+.12,by-.1,.8,.43,str(value),9.5,bold=metric=='Discount',name='value_label')
  f.axis(x,top+3.45,w,70,list(range(0,71,10)),'Cases (out of 70)')
 f.text(.45,12.45,16.9,.42,'Properties overlap; the bars are not additive. Strict changes have positive required score margins.',9.5)
 return f.save()

def fig3(d):
 f=Figure('Figure_3_Scale_Sensitivity','Pointwise sensitivity to the quantisation scale',13.9)
 f.text(.45,.92,16.9,.4,'DL22 naturally incomplete stratum: the same completion is compared across scales',9.5)
 f.text(.45,1.65,16.9,.5,'A  Cases with at least one full-order difference in either profile',10.5,True)
 x=5.15;w=11.6;labels=['10⁴ vs 10⁶','10⁴ vs 10⁸','10⁶ vs 10⁸']
 for k in range(0,13,2):f.line(x+w*k/12,2.5,x+w*k/12,4.8,RULE,.01,'case_grid')
 for i,row in enumerate(d['pairs']):
  y=2.55+i*.78;value=row['cases_with_any_full_order_change']
  f.text(.45,y-.04,4.45,.5,labels[i],10,align='right')
  f.rect(x,y,w*value/12,.32,BLUE,name='affected_cases_bar')
  f.text(x+w*value/12+.12,y-.09,.8,.5,str(value),10,True,name='affected_cases_value')
 f.axis(x,4.95,w,12,list(range(0,13,2)),'Cases (out of 70)')
 f.text(.45,6.55,16.9,.5,'B  Completions where the between-profile disagreement indicator changes',10.5,True)
 f.rect(7.8,7.18,.45,.23,BLUE,name='membership_legend');f.text(8.4,7.05,3.7,.5,'Membership',9.5)
 f.rect(12.15,7.18,.45,.23,GREY,name='prefix_legend');f.text(12.75,7.05,3.8,.5,'Ordered prefix',9.5)
 for k in range(0,3501,500):f.line(x+w*k/3500,7.95,x+w*k/3500,10.65,RULE,.01,'completion_grid')
 for i,row in enumerate(d['pairs']):
  y=8.0+i*.92;f.text(.45,y+.08,4.45,.5,labels[i],10,align='right')
  for j,ep in enumerate(['set','prefix']):
   value=row['agreement_indicator_changed_worlds'][ep];barwidth=w*value/3500
   f.rect(x,y+j*.31,barwidth,.23,BLUE if ep=='set'else GREY,name=f'{ep}_indicator_bar')
   f.text(x+barwidth+.12,y+j*.31-.11,1.0,.45,f'{value:,}',9.5,bold=ep=='set',name='indicator_value')
 f.axis(x,10.85,w,3500,list(range(0,3501,500)),'Completions (out of 144,526,576)')
 f.text(.45,12.45,16.9,.4,'Units differ between panels. Counts carry no probability model and do not establish real-DCG invariance.',9.5)
 f.text(.45,13.02,16.9,.4,'Case-level existence verdicts were unchanged at all three scales for both endpoints.',9.5)
 return f.save()

def main():
 data=json.loads((ROOT/'source_data/figure_data.json').read_text())
 specs=[fig1(data['figure1']),fig2(data['figure2']),fig3(data['figure3'])]
 (ROOT/'source_data/native_objects.json').write_text(json.dumps(specs,indent=2)+'\n')
 print(json.dumps([{k:v for k,v in s.items()if k!='objects'}for s in specs],indent=2))
if __name__=='__main__':main()
