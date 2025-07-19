# Kimchi Tether - 김치프리미엄 자동매매 봇

바이낸스와 업비트 간 가격 차이를 활용한 자동 재정거래(Arbitrage) 봇입니다.

## 주요 기능

- **실시간 가격 모니터링**: 업비트 USDT 마켓의 모든 암호화폐 가격을 바이낸스와 실시간 비교
- **자동 거래 실행**: 수익 기회 포착 시 자동으로 거래 실행
- **양방향 거래 지원** (모두 USDT 기반):
  - 제1축: 업비트 구매 → 바이낸스 판매
  - 제2축: 바이낸스 구매 → 업비트 판매
- **리스크 관리**: 포지션 제한, 손실 한도, 자동 중지 기능
- **상세 로깅**: 모든 거래 및 시스템 상태 기록

## 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/ksw6895/kimchitether.git -b usdt
cd kimchitether
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정
```bash
cp .env.example .env
```

`.env` 파일을 열어 API 키를 입력하세요:
```
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
UPBIT_ACCESS_KEY=your_upbit_access_key
UPBIT_SECRET_KEY=your_upbit_secret_key
```

## 설정 파일 (config.json)

### 주요 설정 항목

- `a_margin.default`: 모든 코인에 적용되는 기본 최소 수익률 마진
- `trade_volume_usdt`: 거래당 기본 USDT 금액
- `fee_data`: 거래소별 거래/출금 수수료 정보
- `risk_management`: 리스크 관리 파라미터

### 설정 예시
```json
{
  "a_margin": {
    "default": 0.004
  },
  "trade_volume_usdt": 1000.0,
  "fee_data": {
    "upbit": {
      "trade": 0.0025
    },
    "binance": {
      "trade": 0.001
    }
  }
}
```

## 실행 방법

```bash
python main.py
```

## 거래 로직

### 제1축 (업비트 → 바이낸스)
1. 업비트에서 코인 매수 (USDT)
2. 바이낸스로 코인 전송
3. 바이낸스에서 코인 매도 (USDT)

### 제2축 (바이낸스 → 업비트)
1. 바이낸스에서 코인 매수 (USDT)
2. 업비트로 코인 전송
3. 업비트에서 코인 매도 (USDT)

## 리스크 관리

- **최대 동시 포지션**: 3개
- **일일 손실 한도**: 1000 USDT
- **최소 잔고 유지**: 500 USDT
- **스톱로스**: 2%

## 로그 파일

- `logs/kimchi_YYYYMMDD.log`: 일별 전체 로그
- `logs/trades.log`: 거래 전용 로그
- `logs/errors.log`: 에러 로그

## 주의사항

1. **API 권한 설정**: 거래소 API에 거래, 출금 권한 필요
2. **자금 준비**: 양 거래소에 충분한 USDT 보유 필요
3. **네트워크 수수료**: 코인별 전송 수수료 고려
4. **법적 규제**: 거주 국가의 암호화폐 거래 규정 확인

## 문제 해결

### API 연결 실패
- API 키/시크릿 확인
- IP 화이트리스트 설정 확인

### 거래 실패
- 잔고 부족 여부 확인
- 최소 거래 금액 확인
- API 권한 확인

## 라이선스

MIT License

## 면책조항

이 봇은 교육 및 연구 목적으로 제작되었습니다. 실제 거래에 사용 시 발생하는 모든 손실에 대한 책임은 사용자에게 있습니다.