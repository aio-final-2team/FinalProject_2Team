# 2026년 6~12월 서울·수도권 공개 급식 식단

수집 기준일은 2026년 11월 24일입니다. 아래 출처에서 날짜와 메뉴를 확인할 수 있는 점심과 간식을 기록했습니다. 기관별 공개 범위에 따라 수록 기간이 다릅니다.

[날짜별 식단 데이터 JSON](public-meals-2026-06-to-12.json)

| 월 | 점심 | 오전 간식 | 오후 간식 | 대표 이미지 |
|---|---:|---:|---:|---:|
| 2026-06 | 65 | 24 | 21 | 6 |
| 2026-07 | 57 | 26 | 22 | 6 |
| 2026-08 | 49 | 25 | 20 | 6 |
| 2026-09 | 84 | 46 | 40 | 6 |
| 2026-10 | 86 | 48 | 41 | 6 |
| 2026-11 | 85 | 50 | 42 | 10 |
| 2026-12 | 26 | 26 | 22 | 10 |

## 공개 출처

- **서울 서대문구 신촌몬테소리유치원 · 6~11월**. 유치원 공통 일별 점심의 월별 공개 조회 API 주소를 JSON에 기록했습니다. 12월 조회 결과는 비어 있었습니다. [공식 급식 게시판](https://www.shinchonkid.com/news/meals)
- **경기 수원시 망포유치원 · 6~11월**. 유치원 공통 주간 중식의 날짜별 주소를 JSON에 기록했습니다. 확인 시점의 12월 주간 조회에서 중식 메뉴가 확인되지 않았습니다. [공식 급식 게시판](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702)
- **서울 강서구 구립아리스타어린이집 · 9~11월**. 공시 식단표의 만 3~5세 일반형 페이지를 기록했습니다. 6~8월은 수록 범위에 포함되지 않습니다. [11월 공시 식단표](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11500000756&flag=DNLL&wkyymm=202611)
- **서울 서초구 서초구립 양재별하어린이집 · 6~11월**. 공시 식단표의 만 3~5세 4찬 일반형을 수록했습니다. 월별 첨부 URL과 PDF 페이지 번호를 JSON에 기록했습니다. [6월 공시 식단표](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11650000423&flag=DNLL&wkyymm=202606) · [서울시 보육포털 기관 페이지](https://iseoul.seoul.go.kr/homepage/main.do?stCode=11650000423)
- **경기 용인시 어린이급식관리지원센터 · 12월**. 11월 20일 공개한 만 3~5세 표준 예정 식단입니다. [용인시 게시글 및 첨부](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822)

JSON의 source_url은 각 날짜가 나온 원문으로 연결합니다. PDF는 source_page, 용인시 식단은 source_attachment_url도 제공합니다. 간식 항목이 비어 있으면 해당 자료에서 메뉴를 확인하지 못한 경우입니다. 11월 24일 이후 날짜는 공개된 예정 식단으로 표시했습니다. 이미지 프롬프트는 대표 이미지가 연결된 JSON 레코드에 기록했습니다.

## 대표 급식 이미지 50장

공개 점심 식단을 바탕으로 ImageGen으로 제작한 가상 급식 이미지입니다. 11월과 12월의 대표 주메뉴가 서로 겹치지 않도록 선정했습니다. 식단표에 대체 메뉴가 있는 경우 기본 메뉴를 중심으로 표현했습니다.

| 날짜 | 기관 | 대표 주메뉴 | 이미지 | 출처 |
|---|---|---|---|---|
| 2026-06-01 | 서초구립 양재별하어린이집 | 쇠불고기 | [이미지 01](images/01-seocho-2026-06-01.webp) | [원문 p.5](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11650000423&flag=DNLL&wkyymm=202606) |
| 2026-06-04 | 신촌몬테소리유치원 | 새우계란볶음밥 | [이미지 02](images/02-shinchon-2026-06-04.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-06-01&to=2026-06-30) |
| 2026-06-10 | 망포유치원 | 돈코츠라멘 | [이미지 03](images/03-mangpo-2026-06-10.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-06-10) |
| 2026-06-15 | 망포유치원 | 양고기큐브스테이크 | [이미지 04](images/04-mangpo-2026-06-15.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-06-15) |
| 2026-06-24 | 망포유치원 | 문어솥밥 | [이미지 05](images/05-mangpo-2026-06-24.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-06-24) |
| 2026-06-27 | 서초구립 양재별하어린이집 | 가지비빔밥 | [이미지 06](images/06-seocho-2026-06-27.webp) | [원문 p.5](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11650000423&flag=DNLL&wkyymm=202606) |
| 2026-07-02 | 망포유치원 | 닭보쌈 | [이미지 07](images/07-mangpo-2026-07-02.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-07-02) |
| 2026-07-07 | 신촌몬테소리유치원 | 순살참치무조림 | [이미지 08](images/08-shinchon-2026-07-07.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-07-01&to=2026-07-31) |
| 2026-07-09 | 신촌몬테소리유치원 | 양념치킨 | [이미지 09](images/09-shinchon-2026-07-09.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-07-01&to=2026-07-31) |
| 2026-07-15 | 망포유치원 | 명란크림파스타 | [이미지 10](images/10-mangpo-2026-07-15.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-07-15) |
| 2026-07-15 | 신촌몬테소리유치원 | 두부간장조림 | [이미지 11](images/11-shinchon-2026-07-15.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-07-01&to=2026-07-31) |
| 2026-07-20 | 망포유치원 | 대패삼겹숙주볶음 | [이미지 12](images/12-mangpo-2026-07-20.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-07-20) |
| 2026-08-04 | 신촌몬테소리유치원 | 한우짜장라이스 | [이미지 13](images/13-shinchon-2026-08-04.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-08-01&to=2026-08-31) |
| 2026-08-06 | 신촌몬테소리유치원 | 브로콜리카레라이스 | [이미지 14](images/14-shinchon-2026-08-06.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-08-01&to=2026-08-31) |
| 2026-08-20 | 신촌몬테소리유치원 | 소고기잡채밥 | [이미지 15](images/15-shinchon-2026-08-20.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-08-01&to=2026-08-31) |
| 2026-08-24 | 망포유치원 | 메쉬드포테이토함박 | [이미지 16](images/16-mangpo-2026-08-24.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-08-24) |
| 2026-08-27 | 망포유치원 | 돼지목살수육 | [이미지 17](images/17-mangpo-2026-08-27.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-08-27) |
| 2026-08-27 | 신촌몬테소리유치원 | 치킨하이라이스 | [이미지 18](images/18-shinchon-2026-08-27.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-08-01&to=2026-08-31) |
| 2026-09-01 | 망포유치원 | 연어된장구이 | [이미지 19](images/19-mangpo-2026-09-01.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-09-01) |
| 2026-09-02 | 망포유치원 | 수제깐쇼새우 | [이미지 20](images/20-mangpo-2026-09-02.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-09-02) |
| 2026-09-04 | 망포유치원 | 낙삼새볶음 | [이미지 21](images/21-mangpo-2026-09-04.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-09-04) |
| 2026-09-09 | 망포유치원 | 새우관자리조또 | [이미지 22](images/22-mangpo-2026-09-09.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-09-09) |
| 2026-09-17 | 망포유치원 | 소갈비찜 | [이미지 23](images/23-mangpo-2026-09-17.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-09-17) |
| 2026-09-23 | 망포유치원 | 궁중떡볶음 | [이미지 24](images/24-mangpo-2026-09-23.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-09-23) |
| 2026-10-02 | 망포유치원 | 주꾸미돈육불고기 | [이미지 25](images/25-mangpo-2026-10-02.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-10-02) |
| 2026-10-06 | 신촌몬테소리유치원 | 비프타코 | [이미지 26](images/26-shinchon-2026-10-06.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-10-01&to=2026-10-31) |
| 2026-10-15 | 망포유치원 | 등갈비바베큐폭립 | [이미지 27](images/27-mangpo-2026-10-15.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-10-15) |
| 2026-10-20 | 신촌몬테소리유치원 | 생안심카츠 | [이미지 28](images/28-shinchon-2026-10-20.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-10-01&to=2026-10-31) |
| 2026-10-27 | 신촌몬테소리유치원 | 미트토마토스파게티 | [이미지 29](images/29-shinchon-2026-10-27.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-10-01&to=2026-10-31) |
| 2026-10-28 | 망포유치원 | 베트남쌀국수 | [이미지 30](images/30-mangpo-2026-10-28.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-10-28) |
| 2026-11-02 | 구립아리스타어린이집 | 들기름두부구이 | [이미지 31](images/31-arista-2026-11-02.webp) | [원문 p.2](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11500000756&flag=DNLL&wkyymm=202611) |
| 2026-11-03 | 구립아리스타어린이집 | 돼지고기김치찜 | [이미지 32](images/32-arista-2026-11-03.webp) | [원문 p.2](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11500000756&flag=DNLL&wkyymm=202611) |
| 2026-11-03 | 신촌몬테소리유치원 | 코다리조림 | [이미지 33](images/33-shinchon-2026-11-03.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-11-01&to=2026-11-30) |
| 2026-11-04 | 신촌몬테소리유치원 | 훈제오리부추볶음 | [이미지 34](images/34-shinchon-2026-11-04.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-11-01&to=2026-11-30) |
| 2026-11-05 | 구립아리스타어린이집 | 고등어조림 | [이미지 35](images/35-arista-2026-11-05.webp) | [원문 p.2](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11500000756&flag=DNLL&wkyymm=202611) |
| 2026-11-11 | 구립아리스타어린이집 | 새우살카레라이스 | [이미지 36](images/36-arista-2026-11-11.webp) | [원문 p.2](https://info.childcare.go.kr/info_html5/pnis/search/PnisFileDownload.jsp?STCODE=11500000756&flag=DNLL&wkyymm=202611) |
| 2026-11-12 | 망포유치원 | LA소갈비구이 | [이미지 37](images/37-mangpo-2026-11-12.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-11-12) |
| 2026-11-18 | 망포유치원 | 가리비낙지칼국수 | [이미지 38](images/38-mangpo-2026-11-18.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-11-18) |
| 2026-11-20 | 신촌몬테소리유치원 | 닭볶음탕 | [이미지 39](images/39-shinchon-2026-11-20.webp) | [원문](https://www.shinchonkid.com/api/daily-meals?from=2026-11-01&to=2026-11-30) |
| 2026-11-24 | 망포유치원 | 순살갈치구이 | [이미지 40](images/40-mangpo-2026-11-24.webp) | [원문](https://mangpo-k.goesw.kr/mangpo-k/ad/fm/foodmenu/selectFoodMenuView.do?mi=4702&schDt=2026-11-24) |
| 2026-12-01 | 용인시어린이급식관리지원센터 | 참치두부스테이크 | [이미지 41](images/41-yongin-2026-12-01.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-02 | 용인시어린이급식관리지원센터 | 오므라이스 | [이미지 42](images/42-yongin-2026-12-02.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-03 | 용인시어린이급식관리지원센터 | 떡갈비조림 | [이미지 43](images/43-yongin-2026-12-03.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-09 | 용인시어린이급식관리지원센터 | 닭가슴살장조림 | [이미지 44](images/44-yongin-2026-12-09.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-10 | 용인시어린이급식관리지원센터 | 삼치구이 | [이미지 45](images/45-yongin-2026-12-10.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-14 | 용인시어린이급식관리지원센터 | 새우살채소볶음 | [이미지 46](images/46-yongin-2026-12-14.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-19 | 용인시어린이급식관리지원센터 | 해물볶음우동 | [이미지 47](images/47-yongin-2026-12-19.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-22 | 용인시어린이급식관리지원센터 | 쇠고기떡찜 | [이미지 48](images/48-yongin-2026-12-22.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-23 | 용인시어린이급식관리지원센터 | 해물토마토자장밥 | [이미지 49](images/49-yongin-2026-12-23.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
| 2026-12-30 | 용인시어린이급식관리지원센터 | 돼지고기가지덮밥 | [이미지 50](images/50-yongin-2026-12-30.webp) | [원문](https://www.yongin.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1019&q_bbscttSn=20261120131205822) |
