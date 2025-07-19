import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objs as go
import plotly.express as px
from datetime import datetime, timedelta
import pandas as pd
from decimal import Decimal
import asyncio
from typing import Dict, List
import json


class TradingDashboard:
    def __init__(self, port: int = 8050):
        self.app = dash.Dash(__name__)
        self.port = port
        self.data_store = {
            'premiums': [],
            'trades': [],
            'metrics': {},
            'balances': {},
            'alerts': []
        }
        self._setup_layout()
        self._setup_callbacks()
        
    def _setup_layout(self):
        self.app.layout = html.Div([
            html.Div([
                html.H1('암호화폐 재정거래 모니터링 대시보드', 
                       style={'textAlign': 'center', 'color': '#2c3e50'}),
                html.Div(id='last-update', style={'textAlign': 'center', 'color': '#7f8c8d'})
            ]),
            
            # Alerts Section
            html.Div(id='alerts-section', style={'margin': '20px'}),
            
            # Key Metrics Row
            html.Div([
                html.Div([
                    html.H3('일일 거래량'),
                    html.H2(id='daily-volume', children='0 KRW')
                ], className='metric-box', style={'width': '23%', 'display': 'inline-block'}),
                
                html.Div([
                    html.H3('일일 수익'),
                    html.H2(id='daily-profit', children='0 KRW')
                ], className='metric-box', style={'width': '23%', 'display': 'inline-block'}),
                
                html.Div([
                    html.H3('성공률'),
                    html.H2(id='success-rate', children='0%')
                ], className='metric-box', style={'width': '23%', 'display': 'inline-block'}),
                
                html.Div([
                    html.H3('활성 거래'),
                    html.H2(id='active-trades', children='0')
                ], className='metric-box', style={'width': '23%', 'display': 'inline-block'}),
            ], style={'margin': '20px', 'textAlign': 'center'}),
            
            # Premium Charts
            html.Div([
                dcc.Graph(id='premium-chart', style={'height': '400px'}),
                dcc.Interval(id='interval-component', interval=5000)  # Update every 5 seconds
            ], style={'margin': '20px'}),
            
            # Balance Information
            html.Div([
                html.Div([
                    html.H3('거래소 잔고'),
                    html.Div(id='balance-info')
                ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),
                
                html.Div([
                    html.H3('최근 거래 내역'),
                    html.Div(id='recent-trades')
                ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'})
            ], style={'margin': '20px'}),
            
            # Hidden div to store data
            html.Div(id='data-store', style={'display': 'none'})
        ])
        
        # Add CSS styling
        self.app.index_string = '''
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>{%title%}</title>
                {%favicon%}
                {%css%}
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        background-color: #ecf0f1;
                        margin: 0;
                        padding: 0;
                    }
                    .metric-box {
                        background-color: white;
                        border-radius: 10px;
                        padding: 20px;
                        margin: 10px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }
                    .metric-box h3 {
                        color: #7f8c8d;
                        margin: 0;
                        font-size: 14px;
                    }
                    .metric-box h2 {
                        color: #2c3e50;
                        margin: 10px 0 0 0;
                        font-size: 24px;
                    }
                    .alert {
                        padding: 15px;
                        margin: 10px;
                        border-radius: 5px;
                        color: white;
                    }
                    .alert-warning {
                        background-color: #f39c12;
                    }
                    .alert-danger {
                        background-color: #e74c3c;
                    }
                    .alert-success {
                        background-color: #27ae60;
                    }
                    .trade-item {
                        background-color: white;
                        padding: 10px;
                        margin: 5px 0;
                        border-radius: 5px;
                        border-left: 4px solid #3498db;
                    }
                    .balance-item {
                        background-color: white;
                        padding: 10px;
                        margin: 5px 0;
                        border-radius: 5px;
                    }
                </style>
            </head>
            <body>
                {%app_entry%}
                <footer>
                    {%config%}
                    {%scripts%}
                    {%renderer%}
                </footer>
            </body>
        </html>
        '''
        
    def _setup_callbacks(self):
        @self.app.callback(
            [Output('daily-volume', 'children'),
             Output('daily-profit', 'children'),
             Output('success-rate', 'children'),
             Output('active-trades', 'children'),
             Output('premium-chart', 'figure'),
             Output('balance-info', 'children'),
             Output('recent-trades', 'children'),
             Output('alerts-section', 'children'),
             Output('last-update', 'children')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_dashboard(n):
            # Update metrics
            metrics = self.data_store.get('metrics', {})
            daily_volume = f"{metrics.get('daily_volume_krw', 0):,.0f} KRW"
            daily_profit = f"{metrics.get('net_profit_krw', 0):,.0f} KRW"
            success_rate = f"{metrics.get('success_rate', 0):.1f}%"
            active_trades = str(metrics.get('active_trades', 0))
            
            # Create premium chart
            premium_data = self.data_store.get('premiums', [])
            if premium_data:
                df = pd.DataFrame(premium_data)
                fig = go.Figure()
                
                for coin in df['coin'].unique():
                    coin_data = df[df['coin'] == coin]
                    fig.add_trace(go.Scatter(
                        x=coin_data['timestamp'],
                        y=coin_data['premium_rate'],
                        mode='lines',
                        name=f'{coin} Premium'
                    ))
                    
                fig.update_layout(
                    title='실시간 프리미엄 추이',
                    xaxis_title='시간',
                    yaxis_title='프리미엄 (%)',
                    hovermode='x unified'
                )
            else:
                fig = go.Figure()
                fig.update_layout(title='프리미엄 데이터 대기중...')
                
            # Update balances
            balances = self.data_store.get('balances', {})
            balance_items = []
            for exchange, balance_data in balances.items():
                for currency, amount in balance_data.items():
                    balance_items.append(
                        html.Div(f"{exchange} - {currency}: {amount:,.2f}", 
                                className='balance-item')
                    )
                    
            # Update recent trades
            trades = self.data_store.get('trades', [])[-10:]  # Last 10 trades
            trade_items = []
            for trade in reversed(trades):
                status_color = '#27ae60' if trade['status'] == 'completed' else '#e74c3c'
                trade_items.append(
                    html.Div([
                        html.Div(f"{trade['coin']} - {trade['direction']}", 
                                style={'fontWeight': 'bold'}),
                        html.Div(f"수익: {trade.get('profit_krw', 0):,.0f} KRW"),
                        html.Div(f"상태: {trade['status']}", 
                                style={'color': status_color})
                    ], className='trade-item')
                )
                
            # Update alerts
            alerts = self.data_store.get('alerts', [])[-5:]  # Last 5 alerts
            alert_items = []
            for alert in alerts:
                alert_class = f"alert alert-{alert['level']}"
                alert_items.append(
                    html.Div(f"{alert['timestamp']} - {alert['message']}", 
                            className=alert_class)
                )
                
            # Update timestamp
            last_update = f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            return (daily_volume, daily_profit, success_rate, active_trades,
                   fig, balance_items, trade_items, alert_items, last_update)
                   
    def update_data(self, data_type: str, data: any):
        """Update dashboard data"""
        if data_type == 'premium':
            self.data_store['premiums'].append(data)
            # Keep only last 1000 entries
            if len(self.data_store['premiums']) > 1000:
                self.data_store['premiums'] = self.data_store['premiums'][-1000:]
                
        elif data_type == 'trade':
            self.data_store['trades'].append(data)
            if len(self.data_store['trades']) > 100:
                self.data_store['trades'] = self.data_store['trades'][-100:]
                
        elif data_type == 'metrics':
            self.data_store['metrics'] = data
            
        elif data_type == 'balances':
            self.data_store['balances'] = data
            
        elif data_type == 'alert':
            self.data_store['alerts'].append({
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'level': data.get('level', 'warning'),
                'message': data.get('message', '')
            })
            if len(self.data_store['alerts']) > 20:
                self.data_store['alerts'] = self.data_store['alerts'][-20:]
                
    def run(self, debug: bool = False):
        """Run the dashboard"""
        self.app.run_server(debug=debug, port=self.port, host='0.0.0.0')