def get_strike_prices(spot_price):
    # Round to nearest 50
    rounded_spot = round(spot_price / 50) * 50

    ce_strike = rounded_spot + 200
    pe_strike = rounded_spot - 200
    hedge_ce = ce_strike + 100
    hedge_pe = pe_strike - 100

    return ce_strike, pe_strike, hedge_ce, hedge_pe
