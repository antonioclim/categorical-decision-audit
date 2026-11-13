/* Extract first strict and conservative-margin witnesses at fixed scale. */
#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
static int before(int a,int b,const int64_t*s){return s[a]>s[b]||(s[a]==s[b]&&a<b);}
static void sw(int*a,int*b,const int64_t*s){if(!before(*a,*b,s)){int t=*a;*a=*b;*b=t;}}
static void order(const int64_t*s,int*o){o[0]=0;o[1]=1;o[2]=2;o[3]=3;sw(o,o+1,s);sw(o+2,o+3,s);sw(o,o+2,s);sw(o+1,o+3,s);sw(o+1,o+2,s);}
int main(void){
 int n;if(scanf("%d",&n)!=1||n<0||n>14)return 2;
 int64_t s[8],q[14][8][4];for(int j=0;j<8;j++)if(scanf("%" SCNd64,s+j)!=1)return 2;
 for(int u=0;u<n;u++)for(int j=0;j<8;j++)for(int d=0;d<4;d++)if(scanf("%" SCNd64,&q[u][j][d])!=1)return 2;
 for(int u=0;u<n;u++)for(int j=0;j<8;j++)s[j]+=q[u][j][0];
 int grades[14]={0};int64_t found[2][2]={{-1,-1},{-1,-1}};uint64_t worlds=UINT64_C(1)<<(2*n),evaluated=0;
 for(uint64_t w=0;w<worlds;w++){
  int b[4],g[4];order(s,b);order(s+4,g);
  int cs=b[3]!=g[3],cp=b[0]!=g[0]||b[1]!=g[1]||b[2]!=g[2];
  int64_t bcut=s[b[2]]-s[b[3]],gcut=s[4+g[2]]-s[4+g[3]];
  int strictset=cs&&bcut>0&&gcut>0,robustset=cs&&bcut>20&&gcut>20;
  int strictprefix=cp,robustprefix=cp;
  for(int k=0;k<3;k++){int64_t bg=s[b[k]]-s[b[k+1]],gg=s[4+g[k]]-s[4+g[k+1]];strictprefix=strictprefix&&bg>0&&gg>0;robustprefix=robustprefix&&bg>20&&gg>20;}
  if(strictset&&found[0][0]<0)found[0][0]=(int64_t)w;
  if(robustset&&found[0][1]<0)found[0][1]=(int64_t)w;
  if(strictprefix&&found[1][0]<0)found[1][0]=(int64_t)w;
  if(robustprefix&&found[1][1]<0)found[1][1]=(int64_t)w;
  evaluated++;
  if((found[0][1]>=0&&found[1][1]>=0)||w+1==worlds)break;
  for(int u=n-1;u>=0;u--){int old=grades[u],d=(old+1)&3;grades[u]=d;for(int j=0;j<8;j++)s[j]+=q[u][j][d]-q[u][j][old];if(d!=0)break;}
 }
 printf("{\"worlds\":%" PRIu64 ",\"completions_evaluated\":%" PRIu64 ",\"set_strict\":%" PRId64 ",\"set_margin_gt20\":%" PRId64 ",\"prefix_strict\":%" PRId64 ",\"prefix_margin_gt20\":%" PRId64 "}\n",worlds,evaluated,found[0][0],found[0][1],found[1][0],found[1][1]);return 0;
}
