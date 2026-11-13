/* Independent finite traversal of four-run integer score tables.
 * Input: n_unknown, eight known scores, then 8*4 coefficients per unknown.
 * Enumeration shares each grade across all runs/profiles. All sums int64.
 * This program does not read portable records, proof rows or checker code.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>

static int precedes(int a, int b, const int64_t *s) {
    return s[a] > s[b] || (s[a] == s[b] && a < b);
}
static void compare_swap(int *a, int *b, const int64_t *s) {
    if (!precedes(*a, *b, s)) { int t=*a; *a=*b; *b=t; }
}
static void ranking(const int64_t *s, int *o) {
    o[0]=0; o[1]=1; o[2]=2; o[3]=3;
    compare_swap(&o[0],&o[1],s); compare_swap(&o[2],&o[3],s);
    compare_swap(&o[0],&o[2],s); compare_swap(&o[1],&o[3],s);
    compare_swap(&o[1],&o[2],s);
}
static int code(const int *o) { return o[0]*64+o[1]*16+o[2]*4+o[3]; }
int main(void) {
    int n;
    if (scanf("%d",&n)!=1 || n<0 || n>14) return 2;
    int64_t scores[8], q[14][8][4];
    for(int j=0;j<8;j++) if(scanf("%" SCNd64,&scores[j])!=1) return 2;
    for(int u=0;u<n;u++) for(int j=0;j<8;j++) for(int d=0;d<4;d++)
        if(scanf("%" SCNd64,&q[u][j][d])!=1 || q[u][j][d]<0) return 2;
    int map[256]; for(int i=0;i<256;i++) map[i]=-1;
    int idx=0;
    for(int a=0;a<4;a++) for(int b=0;b<4;b++) for(int c=0;c<4;c++) for(int d=0;d<4;d++)
        if(a!=b&&a!=c&&a!=d&&b!=c&&b!=d&&c!=d) map[a*64+b*16+c*4+d]=idx++;
    int grades[14]={0};
    for(int u=0;u<n;u++) for(int j=0;j<8;j++) scores[j]+=q[u][j][0];
    uint64_t joint[24][24]={{0}};
    uint64_t changed_set=0,changed_prefix=0,strict_set=0,strict_prefix=0;
    uint64_t robust_set=0,robust_prefix=0;
    uint64_t worlds=UINT64_C(1)<<(2*n);
    for(uint64_t w=0;w<worlds;w++) {
        int b[4],g[4]; ranking(scores,b); ranking(scores+4,g);
        joint[map[code(b)]][map[code(g)]]++;
        int cs=b[3]!=g[3],cp=code(b)!=code(g);
        changed_set+=cs; changed_prefix+=cp;
        int64_t bg=scores[b[2]]-scores[b[3]],gg=scores[4+g[2]]-scores[4+g[3]];
        strict_set+=(cs && bg>0 && gg>0);
        robust_set+=(cs && bg>20 && gg>20);
        int sp=cp,rp=cp;
        for(int k=0;k<3;k++) {
            int64_t x=scores[b[k]]-scores[b[k+1]], y=scores[4+g[k]]-scores[4+g[k+1]];
            sp=sp && x>0 && y>0; rp=rp && x>20 && y>20;
        }
        strict_prefix+=sp; robust_prefix+=rp;
        if(w+1==worlds) break;
        for(int u=n-1;u>=0;u--) {
            int old=grades[u],d=(old+1)&3; grades[u]=d;
            for(int j=0;j<8;j++) scores[j]+=q[u][j][d]-q[u][j][old];
            if(d!=0) break;
        }
    }
    printf("{\"worlds\":%" PRIu64 ",\"set_change_worlds\":%" PRIu64 ",\"prefix_change_worlds\":%" PRIu64 ",\"strict_set_change_worlds\":%" PRIu64 ",\"strict_prefix_change_worlds\":%" PRIu64 ",\"margin_gt20_set_change_worlds\":%" PRIu64 ",\"margin_gt20_prefix_change_worlds\":%" PRIu64 ",\"joint\":[",worlds,changed_set,changed_prefix,strict_set,strict_prefix,robust_set,robust_prefix);
    for(int b=0;b<24;b++) for(int g=0;g<24;g++) printf("%s%" PRIu64,b||g?",":"",joint[b][g]);
    puts("]}");
    return 0;
}
