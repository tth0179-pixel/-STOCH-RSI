# 코스피 TOP 20 Stoch RSI 스크리너

코스피 시가총액 상위 20개 종목(최초 실행 시 고정)을 대상으로 일봉/주봉/월봉 Stoch RSI를 계산해
아이폰 사파리에서도 볼 수 있는 웹페이지로 보여주는 개인용 도구입니다.

## 구성
- `fetch_data.py` — pykrx로 시세를 받아 Stoch RSI를 계산하고 `data.json`으로 저장
- `top20_codes.json` — 처음 실행 시 확정된 시총 20위 종목 코드 (고정 리스트)
- `data.json` — 계산 결과 (지금 들어있는 값은 화면 미리보기용 샘플입니다)
- `index.html` — `data.json`을 읽어 보여주는 대시보드 화면
- `.github/workflows/update.yml` — 매 평일 장마감 후 자동으로 데이터 갱신

## 배포 방법 (GitHub Pages, 완전 무료)

1. GitHub에 새 저장소를 만들고 이 폴더 전체를 업로드합니다.
2. 저장소 **Settings → Pages** 에서 Source를 `main` 브랜치 / `/ (root)`로 설정합니다.
3. **Settings → Actions → General → Workflow permissions** 에서
   "Read and write permissions"을 선택합니다. (자동 커밋을 위해 필요)
4. **Actions** 탭에서 `Update KOSPI Stoch RSI Data` 워크플로우를 한 번 수동 실행(`Run workflow`)해서
   실제 데이터로 `data.json`을 갱신합니다.
5. 몇 분 후 `https://<사용자아이디>.github.io/<저장소이름>/` 주소로 접속하면 결과가 보입니다.
6. 아이폰 사파리에서 해당 주소를 열고 공유 버튼 → "홈 화면에 추가"를 하면 앱처럼 아이콘으로 쓸 수 있습니다.

이후에는 매 평일 16:30(KST)에 자동으로 데이터가 갱신됩니다.

## 로컬에서 먼저 테스트하고 싶다면
```bash
pip install -r requirements.txt
python fetch_data.py   # data.json, top20_codes.json 생성
python -m http.server 8000
# 브라우저에서 http://localhost:8000 접속
```

## 참고
- "신호" 배지는 %K가 20 이하 과매도 구간에 있으면서 %D 이상으로 올라온 종목에 표시됩니다 (매수 관심 신호).
- 시총 20위 종목을 다시 새로 뽑고 싶으면 `top20_codes.json`을 삭제하고 워크플로우를 다시 실행하세요.
