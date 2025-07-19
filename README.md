# 암호화폐 재정거래 자동매매 봇

국내(Upbit)와 해외(Binance) 거래소 간 가격 차이를 활용한 자동 재정거래 시스템입니다.

## 주요 기능

- **실시간 프리미엄 모니터링**: 김치프리미엄 및 역프리미엄 실시간 추적
- **양방향 재정거래**: 
  - 정방향 거래 (역프리미엄 활용): Upbit 매수 → Binance 매도
  - 역방향 거래 (김치프리미엄 활용): Binance 매수 → Upbit 매도
- **리스크 관리**: 
  - 환율 정보 실패 시 거래 중단
  - 일일 거래량 제한
  - 긴급 정지 시스템
  - 슬리피지 모니터링
- **실시간 대시보드**: 웹 기반 모니터링 대시보드
- **안전장치**: 최소 수익률(safety margin) 설정으로 리스크 방지

## 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/ksw6895/kimchitether.git
cd kimchitether
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정
```bash
cp .env.example .env
```

`.env` 파일을 열어 필요한 API 키와 설정을 입력하세요:

```env
# Binance API Keys
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_key_here

# Upbit API Keys
UPBIT_ACCESS_KEY=your_upbit_access_key_here
UPBIT_SECRET_KEY=your_upbit_secret_key_here

# Trading Parameters
SAFETY_MARGIN_PERCENT=1.5  # 최소 목표 수익률
MIN_TRADE_AMOUNT_KRW=100000
MAX_TRADE_AMOUNT_KRW=5000000
```

## 실행 방법

### 실거래 모드
```bash
python main.py
```

### 모의거래 모드 (실제 거래 없이 시뮬레이션)
```bash
DRY_RUN=true python main.py
```

### 대시보드 접속
봇 실행 후 웹 브라우저에서 `http://localhost:8050` 접속

## 거래 로직

### 정방향 거래 (역프리미엄 활용)
```
조건: [코인 역프율(%)] - [테더 역프율(%)] > [통합 수수료(%)] + a(%)

1. Upbit에서 원화로 코인 매수
2. 코인을 Binance로 전송
3. Binance에서 코인을 USDT로 매도
4. USDT를 Upbit으로 전송
5. Upbit에서 USDT를 원화로 매도
```

### 역방향 거래 (김치프리미엄 활용)
```
조건: [코인 김치프리미엄(%)] - [테더 김치프리미엄(%)] > [통합 수수료(%)] + a(%)

1. Binance에서 USDT로 코인 매수
2. 코인을 Upbit으로 전송
3. Upbit에서 코인을 원화로 매도
4. 원화로 USDT 매수
5. USDT를 Binance로 전송
```

## 주요 설정

### config.py에서 설정 가능한 항목:
- `monitor_coins`: 모니터링할 코인 목록
- `safety_margin_percent`: 안전 마진 (a 값)
- `max_concurrent_trades`: 최대 동시 거래 수
- `max_daily_volume_krw`: 일일 최대 거래량
- `emergency_stop_loss_percent`: 긴급 정지 손실률

## 안전 기능

1. **환율 정보 실패 시 거래 중단**: 환율 정보를 가져올 수 없으면 자동으로 거래 중단
2. **일일 거래량 제한**: 설정된 일일 최대 거래량 초과 방지
3. **동시 거래 제한**: 리스크 분산을 위한 동시 거래 수 제한
4. **긴급 정지**: 손실률이 임계값을 초과하면 자동 거래 중단
5. **슬리피지 보호**: 과도한 슬리피지 발생 시 거래 취소

## 주의사항

- 실거래 전 반드시 소액으로 테스트하세요
- API 키는 출금 권한이 필요합니다
- 네트워크 수수료와 전송 시간을 고려하세요
- 시장 상황에 따라 손실이 발생할 수 있습니다

## 라이선스

MIT License