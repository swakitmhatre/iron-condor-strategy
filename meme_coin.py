[RECENT 5m CANDLE OHLC & INDICATOR METRICS]
  TIMESTAMP (UTC)    | OPEN         | HIGH         | LOW          | CLOSE        | RSI    | MACD HIST    | ST TREND
  --------------------------------------------------------------------------------------------------------
  2026-10-31 08:15   | 0.000003     | 0.000003     | 0.000003     | 0.000003     | 0.0    | 0.00e+00     | BULL
  2026-10-31 08:35   | 0.000003     | 0.000004     | 0.000003     | 0.000003     | 0.0    | 0.00e+00     | BULL
  2026-10-31 08:40   | 0.000003     | 0.000004     | 0.000003     | 0.000004     | 0.0    | 0.00e+00     | BULL
  2026-10-31 08:45   | 0.000004     | 0.000005     | 0.000004     | 0.000004     | 0.0    | 0.00e+00     | BULL
  2026-10-31 08:50   | 0.000004     | 0.000007     | 0.000004     | 0.000006     | 0.0    | 0.00e+00     | BULL
  --------------------------------------------------------------------------------------------------------

  [MAIN PANEL: CANDLESTICK CHART (PRICE & WICKS)]

   $0.000007 |           │ 
   $0.000006 |           █ 
   $0.000006 |           █ 
   $0.000005 |           █ 
   $0.000005 |         │ █ 
   $0.000004 |       █ █ █ 
   $0.000004 |     │ █ │   
   $0.000004 |     █ █     
   $0.000003 | █ █ █       
   $0.000003 | █           
             ------------
  Timeline   | 08:10 08:40 08:50 UTC

  [SUBPANEL 1: MACD HISTOGRAM]
Traceback (most recent call last):
  File "/home/ubuntu/iron-condor-strategy/venv/lib/python3.12/site-packages/pandas/core/indexes/base.py", line 3816, in get_loc
    return self._engine.get_loc(casted_key)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "pandas/_libs/index.pyx", line 172, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/index.pyx", line 201, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/hashtable_class_helper.pxi", line 7726, in pandas._libs.hashtable.PyObjectHashTable.get_item
  File "pandas/_libs/hashtable_class_helper.pxi", line 7734, in pandas._libs.hashtable.PyObjectHashTable.get_item
KeyError: 'MACD_hist'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/ubuntu/iron-condor-strategy/meme_coin.py", line 261, in <module>
    main()
  File "/home/ubuntu/iron-condor-strategy/meme_coin.py", line 255, in main
    print_tradingview_terminal_dashboard(coin['symbol'], coin['pairAddress'], df)
  File "/home/ubuntu/iron-condor-strategy/meme_coin.py", line 176, in print_tradingview_terminal_dashboard
    for mh in plot_df['MACD_hist']:
              ~~~~~~~^^^^^^^^^^^^^
  File "/home/ubuntu/iron-condor-strategy/venv/lib/python3.12/site-packages/pandas/core/frame.py", line 4330, in __getitem__
    indexer = self.columns.get_loc(key)
              ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/ubuntu/iron-condor-strategy/venv/lib/python3.12/site-packages/pandas/core/indexes/base.py", line 3823, in get_loc
    raise KeyError(key) from err
KeyError: 'MACD_hist'
((venv) ) ubuntu@ip-172-31-4-168:~/iron-condor-strategy$ 
