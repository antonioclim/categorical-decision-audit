/* Shared-completion sensitivity of three certified quantisation scales.
 * Input n_unknown, 24 fixed scores then n*24*4 integer contributions.
 * Scores indexed scale-major, binary then graded, four lexical run indices.
 */
#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
#include <limits.h>
static int before(int a,int b,const int64_t *s){return s[a]>s[b]||(s[a]==s[b]&&a<b);}
static void sw(int*a,int*b,const int64_t*s){if(!before(*a,*b,s)){int t=*a;*a=*b;*b=t;}}
static void order(const int64_t*s,int*o){o[0]=0;o[1]=1;o[2]=2;o[3]=3;sw(o,o+1,s);sw(o+2,o+3,s);sw(o,o+2,s);sw(o+1,o+3,s);sw(o+1,o+2,s);}
static int code(const int*o){return o[0]*64+o[1]*16+o[2]*4+o[3];}
int main(void){
 int n;if(scanf("%d",&n)!=1||n<0||n>14)return 2;
 int64_t s[24],q[14][24][4];
 for(int j=0;j<24;j++)if(scanf("%" SCNd64,s+j)!=1)return 2;
 for(int u=0;u<n;u++)for(int j=0;j<24;j++)for(int d=0;d<4;d++)if(scanf("%" SCNd64,&q[u][j][d])!=1)return 2;
 int grades[14]={0};for(int u=0;u<n;u++)for(int j=0;j<24;j++)s[j]+=q[u][j][0];
 uint64_t worlds=UINT64_C(1)<<(2*n),change[3][2][2]={{{0}}},indicator[3][2]={{0}},anyorder[3]={0};
 uint64_t cut_tie[6]={0},any_tie[6]={0},small_cut[6]={0},small_any[6]={0};
 int64_t min_cut[6],min_any[6];for(int j=0;j<6;j++){min_cut[j]=INT64_MAX;min_any[j]=INT64_MAX;}
 int pairs[3][2]={{0,1},{0,2},{1,2}};
 for(uint64_t w=0;w<worlds;w++){
  int o[6][4],codes[6],delta[3][2];
  for(int j=0;j<6;j++){
   order(s+4*j,o[j]);codes[j]=code(o[j]);int at=0,sa=0;
   for(int k=0;k<3;k++){
    int64_t g=s[4*j+o[j][k]]-s[4*j+o[j][k+1]];
    at|=g==0;sa|=g>0&&g<=20;
    if(g>0&&g<min_any[j])min_any[j]=g;
    if(k==2){cut_tie[j]+=g==0;small_cut[j]+=g>0&&g<=20;if(g>0&&g<min_cut[j])min_cut[j]=g;}
   }
   any_tie[j]+=at;small_any[j]+=sa;
  }
  for(int a=0;a<3;a++){delta[a][0]=o[2*a][3]!=o[2*a+1][3];delta[a][1]=codes[2*a]!=codes[2*a+1];}
  for(int p=0;p<3;p++){
   int a=pairs[p][0],b=pairs[p][1];anyorder[p]+=codes[2*a]!=codes[2*b]||codes[2*a+1]!=codes[2*b+1];
   for(int profile=0;profile<2;profile++){change[p][profile][0]+=o[2*a+profile][3]!=o[2*b+profile][3];change[p][profile][1]+=codes[2*a+profile]!=codes[2*b+profile];}
   for(int e=0;e<2;e++)indicator[p][e]+=delta[a][e]!=delta[b][e];
  }
  if(w+1==worlds)break;
  for(int u=n-1;u>=0;u--){int old=grades[u],d=(old+1)&3;grades[u]=d;for(int j=0;j<24;j++)s[j]+=q[u][j][d]-q[u][j][old];if(d!=0)break;}
 }
 printf("{\"worlds\":%" PRIu64 ",\"output_changes\":[",worlds);
 for(int p=0;p<3;p++)for(int j=0;j<2;j++)for(int e=0;e<2;e++)printf("%s%" PRIu64,p||j||e?",":"",change[p][j][e]);
 printf("],\"indicator_changes\":[");for(int p=0;p<3;p++)for(int e=0;e<2;e++)printf("%s%" PRIu64,p||e?",":"",indicator[p][e]);
 printf("],\"any_order_changes\":[");for(int p=0;p<3;p++)printf("%s%" PRIu64,p?",":"",anyorder[p]);
 printf("],\"cut_ties\":[");for(int j=0;j<6;j++)printf("%s%" PRIu64,j?",":"",cut_tie[j]);
 printf("],\"any_ties\":[");for(int j=0;j<6;j++)printf("%s%" PRIu64,j?",":"",any_tie[j]);
 printf("],\"small_positive_cut\":[");for(int j=0;j<6;j++)printf("%s%" PRIu64,j?",":"",small_cut[j]);
 printf("],\"small_positive_any\":[");for(int j=0;j<6;j++)printf("%s%" PRIu64,j?",":"",small_any[j]);
 printf("],\"min_positive_cut\":[");for(int j=0;j<6;j++)printf("%s%" PRId64,j?",":"",min_cut[j]==INT64_MAX?-1:min_cut[j]);
 printf("],\"min_positive_any\":[");for(int j=0;j<6;j++)printf("%s%" PRId64,j?",":"",min_any[j]==INT64_MAX?-1:min_any[j]);
 puts("]}");return 0;
}
