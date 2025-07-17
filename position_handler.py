# position_handler.py

from utils import *
from datetime import datetime

class PositionHandler:
    def __init__(self, trader):
        self.trader = trader
        self.positions = []
        self.entry_time = None
        self.margin = 0

    def execute_iron_condor(self):
        spot = self.trader.get_nifty_spot()
        atm = round(spot / 50) * 50

        sell_ce = atm + 200
        sell_pe = atm - 200
        buy_ce = sell_ce + 100
        buy_pe = sell_pe - 100

        orders = [
            {"security": f"NIFTY{buy_ce}CE", "action": "BUY"},
            {"security": f"NIFTY{buy_pe}PE", "action": "BUY"},
            {"security": f"NIFTY{sell_ce}CE", "action": "SELL"},
            {"security": f"NIFTY{sell_pe}PE", "action": "SELL"},
        ]

        self.margin = self.trader.get_margin_required(orders)["total"]

        for order in orders:
            res = self.trader.place_order(order)
            self.positions.append(res["order_id"])

        self.entry_time = datetime.now()
        log_message(f"Entered Iron Condor at spot {spot}, Margin: {self.margin}")

    def exit_all_positions(self, reason="Manual"):
        for order_id in self.positions:
            self.trader.exit_position(order_id)
        log_message(f"Exited all positions due to {reason}.")

    def check_mtm_targets(self):
        profit = 0.002 * self.margin
        # Simulated MTM (real logic can query net positions)
        current_pnl = profit + 1
        if current_pnl >= profit:
            log_message(f"MTM Target hit ({current_pnl:.2f}). Exiting.")
            self.exit_all_positions(reason="MTM Target Hit")
            return True
        return False

    def check_intraday_movement(self):
        # Simulate for now
        moved = False
        if moved:
            log_message("NIFTY moved >1% intraday. Exiting.")
            self.exit_all_positions(reason=">1% NIFTY Move")
            return True
        return False
