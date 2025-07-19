# 바이낸스(Binance) & 업비트(Upbit) 거래소 API 문서 조사 결과

## 1. 바이낸스(Binance) API

### 1.1 현재가 조회 엔드포인트
- **Symbol Price Ticker**: `GET /api/v3/ticker/price`
  - 현재 거래 가격 반환
  - 특정 심볼 또는 모든 심볼의 가격 조회 가능
  
- **24hr Ticker Statistics**: `GET /api/v3/ticker/24hr`
  - 24시간 가격 통계 정보
  - 가격 변동, 고가/저가, 거래량 포함

### 1.2 시장가 매수/매도 주문 방법
- **엔드포인트**: `POST /api/v3/order`
- **필수 파라미터**:
  - `symbol`: 거래 쌍 (예: "BTCUSDT")
  - `side`: "BUY" 또는 "SELL"
  - `type`: "MARKET"
  - `quantity` 또는 `quoteOrderQty`
- **응답 타입**: ACK, RESULT, FULL 중 선택 가능

### 1.3 출금 API 사용법
- **출금 요청**: `POST /sapi/v1/capital/withdraw/apply (HMAC SHA256)`
  - `withdrawOrderId`: 사용자 정의 출금 ID 지원
- **출금 내역 조회**: `GET /sapi/v1/capital/withdraw/history (HMAC SHA256)`
  - `limit` 파라미터: 기본값 1000, 최대값 1000

### 1.4 입금 주소 조회 방법
- **엔드포인트**: `GET /sapi/v1/capital/deposit/address (HMAC SHA256)`
- **네트워크별 입금 주소 조회 가능**
- **모든 코인 정보 조회**: `GET /sapi/v1/capital/config/getall (HMAC SHA256)`
  - `minConfirm`: 잔액 확인을 위한 최소 컨펌 수
  - `unLockConfirm`: 잔액 언락을 위한 컨펌 수

### 1.5 입금 확인 방법
- **입금 내역 조회**: `GET /sapi/v1/capital/deposit/hisrec (HMAC SHA256)`
- 네트워크별 입금 내역 확인 가능

### 1.6 API 인증 방법
- **API Key 구조**:
  - API Key: 공개 키
  - Secret Key: 비밀 키 (절대 공유 금지)
  
- **인증 요구사항**:
  - TRADE, MARGIN, USER_DATA 엔드포인트는 SIGNED 엔드포인트
  - HMAC SHA256 서명 사용
  - `timestamp` 파라미터 필수 (밀리초 타임스탬프)
  - `signature` 파라미터로 서명 전송
  
- **보안 권장사항**:
  - IP 화이트리스트 설정 (강력 권장)
  - API 키는 대소문자 구분

### 1.7 Rate Limit 정보
- **IP 기반 제한**: 분당 6000 요청 (API 키가 아닌 IP 기준)
- **WebSocket 제한**:
  - 초당 5개 메시지 수신 제한
  - 단일 연결당 최대 1024 스트림
  - IP당 5분마다 300 연결 시도 제한
  
- **Rate Limit 모니터링**:
  - `X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)`: 현재 IP의 사용 가중치
  - `X-MBX-ORDER-COUNT-(intervalNum)(intervalLetter)`: 주문 수 표시
  
- **HTTP 응답 코드**:
  - 429: Rate limit 초과
  - 418: 429 이후 계속 요청 시 자동 차단

- **2025년 업데이트 예정**:
  - 2025년 2월 26일부터 WebSocket ping 간격 변경 (3분 → 20초)
  - 2025년 6월 12일: SBE 2:0 스키마 폐기

## 2. 업비트(Upbit) API

### 2.1 현재가 조회 엔드포인트
- 공개 API (QUOTATION API)는 access_key와 secret_key 불필요
- Market, Candle, Trade 섹션에서 가격 정보 조회 가능

### 2.2 시장가 매수/매도 주문 방법
- **주문 타입**: 시장가, 지정가, 스탑-리밋 주문 지원
- 모든 마켓에서 스탑-리밋 주문이 가능한 것은 아님

### 2.3 출금 API 사용법
```python
from upbit.client import Upbit
access_key = "Your Access Key"
secret_key = "Your Secret Key"
client = Upbit(access_key, secret_key)
resp = client.Withdraw.Withdraw_chance(
    currency='BTC',
    net_type='BTC'
)
```

### 2.4 입금 주소 조회 방법
```python
from upbit.client import Upbit
access_key = "Your Access Key"
secret_key = "Your Secret Key"
client = Upbit(access_key, secret_key)
resp = client.Deposit.Deposit_coin_address(
    currency='BTC',
    net_type='BTC'
)
```
- 주의: 입금 주소 생성 요청 후 아직 발급되지 않은 경우 `deposit_address`가 null일 수 있음

### 2.5 입금 확인 방법
- 입금 API를 통해 입금 내역 및 상태 확인 가능
- 검증 레벨에 따른 입출금 제한:
  - Level 2: 암호화폐 입금 가능
  - Level 4: 법정화폐 거래 가능

### 2.6 API 인증 방법
- **인증 요구사항**:
  - Access Key와 Secret Key 사용
  - JWT 형식 토큰 생성
  - HS256 서명 방식 권장
  - Authorization 헤더로 토큰 전송
  
- **중요 사항**:
  - Secret Key는 base64 인코딩되지 않음
  - Secret Key는 한 번만 발급되며 재확인 불가 (안전하게 보관 필수)
  - Open API Key 토큰 유효기간: 1년 (연장 불가)

### 2.7 Rate Limit 정보
- **응답 헤더 형식**: `Remaining-Req: group=default; min=1800; sec=29`
  - "default" 그룹 내에서 현재 초에 29개 요청 가능
  
- **Rate Limit 초과 시**:
  - 429 Too Many Requests 에러 발생
  - 초당 및 분당 제한 모두 적용
  - 첫 요청 시간 기준으로 계산, 일정 시간 후 리셋
  - 실패한 요청은 제한에 포함되지 않음
  
- **권장사항**: 
  - 여러 REST API 요청이 필요한 경우 WebSocket 사용 권장

## 3. 두 거래소 비교

### 3.1 거래 수수료 구조
- **바이낸스**:
  - 기본 수수료: Maker/Taker 모두 0.1%
  - BNB로 수수료 지불 시 0.075%로 할인
  - VIP 레벨에 따라 추가 할인 가능
  
- **업비트**:
  - 기본 수수료: Maker/Taker 모두 0.25%
  - SGD, BTC, USDT 마켓별로 수수료 상이 (0.2%-0.25%)

### 3.2 출금 수수료 정보
- **바이낸스**:
  - 암호화폐별로 상이
  - 비트코인(BTC): 
    - Lightning Network: 0.000001 BTC
    - BEP2: 0.0000041 BTC
    - 최소 출금: 0.0004 BTC
  - 네트워크 수수료는 실시간 변동
  
- **업비트**:
  - 암호화폐별로 상이
  - 비트코인(BTC): 0.0005 BTC
  - 입금 수수료 없음

### 3.3 지원하는 암호화폐
- **바이낸스**: 400개 이상의 암호화폐 지원
- **업비트**: 200개 이상의 암호화폐 지원

### 3.4 공통 거래 가능 코인
두 거래소 모두에서 거래 가능한 주요 암호화폐:
- BTC (Bitcoin)
- ETH (Ethereum)
- USDT (Tether)
- USDC (USD Coin)
- 기타 주요 암호화폐들

### 3.5 기타 차이점
- **사용자 기반**: 바이낸스 약 2.24억 명, 업비트 약 890만 명
- **지역 제한**: 업비트는 미국 거주자에게 서비스 제공 불가
- **API 토큰 유효기간**: 업비트 API 키는 1년 유효기간 (연장 불가)

## 4. API 사용 시 주의사항

### 바이낸스
- 2025년 2월 26일부터 WebSocket 서비스 변경 예정
- API 타임아웃: 10초
- 서버 시간 + 1초 이상의 timestamp는 거부됨

### 업비트
- JWT 서명 방식 변경 가능성 있음
- 미국 거주자 서비스 이용 불가
- API 키 만료 시 재발급 필요

## 5. 공식 문서 링크
- **바이낸스**: https://developers.binance.com/docs/binance-spot-api-docs
- **업비트**: https://global-docs.upbit.com/