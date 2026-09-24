python -c "from tradingview_screener import Query; print(Query().set_tickers('TADAWUL:2222', 'TADAWUL:1120').select('name', 'close', 'change').get_scanner_data())"
