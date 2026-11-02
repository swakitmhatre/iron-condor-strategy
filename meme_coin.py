def render_terminal_chart(coin_name, df):
    """Renders clean individual terminal charts using Plotext v6 syntax standards."""
    if df.empty or len(df) < 2:
        print(f"[Info] Insufficient candles to plot for {coin_name}")
        return

    closes = df["close"].tolist()
    st = df["supertrend"].tolist()
    macd_hist = df["macd_hist"].tolist()
    macd = df["macd"].tolist()
    signal = df["macd_signal"].tolist()
    rsi = df["rsi"].tolist()
    x_indices = list(range(len(closes)))

    print("\n" + "="*50)
    print(f">>> TERMINAL CHARTS FOR: {coin_name} [{pd.Timestamp.now()}]")
    print("="*50)

    # --- Chart 1: Price Action & Supertrend ---
    fig1 = plt.figure
    fig1.clear()
    fig1.plot_size(90, 14)
    fig1.title(f"{coin_name} - Price vs Supertrend (10,3)")
    
    sig_close = fig1.signal(x_indices, closes)
    sig_close.lines()
    fig1.draw(sig_close)
    fig1.label("Close Price", 0)

    sig_st = fig1.signal(x_indices, st)
    sig_st.lines()
    fig1.draw(sig_st)
    fig1.label("Supertrend", 1)
    
    fig1.show()
    print("-" * 50)

    # --- Chart 2: MACD Histogram & Lines ---
    fig2 = plt.figure
    fig2.clear()
    fig2.plot_size(90, 12)
    fig2.title(f"{coin_name} - MACD (8,17,9)")
    
    if len(macd_hist) > 0:
        binx, biny = hist_data(macd_hist, bins=8)
        fig2.axes(False)
        bar_sig = fig2.bar(binx, biny, orientation="vertical", marker="brick", width=0.6)
        fig2.draw(bar_sig)

    sig_macd = fig2.signal(x_indices, macd)
    sig_macd.lines()
    fig2.draw(sig_macd)
    fig2.label("MACD Line", 1)

    sig_sig = fig2.signal(x_indices, signal)
    sig_sig.lines()
    fig2.draw(sig_sig)
    fig2.label("Signal Line", 2)

    fig2.show()
    print("-" * 50)

    # --- Chart 3: RSI (14) ---
    fig3 = plt.figure
    fig3.clear()
    fig3.plot_size(90, 10)
    fig3.title(f"{coin_name} - RSI (14)")
    
    sig_rsi = fig3.signal(x_indices, rsi)
    sig_rsi.lines()
    fig3.draw(sig_rsi)
    fig3.label("RSI Value", 0)
    
    fig3.ruler("y").lim(0, 100)
    fig3.show()
    print("="*50 + "\n")
