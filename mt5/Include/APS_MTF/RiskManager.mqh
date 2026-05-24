//+------------------------------------------------------------------+
//|                                               RiskManager.mqh    |
//|  Position sizing, SL/TP, trailing stop, daily-loss / streak       |
//|  circuit breakers.                                                |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_RISK_MANAGER_MQH__
#define __APS_MTF_RISK_MANAGER_MQH__

#include <Trade/Trade.mqh>

class CRiskManager
  {
private:
   string             m_symbol;
   long               m_magic;
   string             m_comment;
   double             m_risk_pct;
   double             m_sl_atr_mult;
   double             m_tp_rr;
   double             m_trail_start_rr;
   double             m_max_daily_loss_pct;
   int                m_max_consec_losses;
   int                m_atr_handle;
   CTrade             m_trade;

   double             m_session_start_equity;
   datetime           m_session_date;
   int                m_consec_losses;
   datetime           m_lockout_until_date;

   ENUM_TIMEFRAMES    m_atr_tf;
   int                m_atr_period;

   double             SymbolMinLot() const  { return SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);  }
   double             SymbolMaxLot() const  { return SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);  }
   double             SymbolLotStep() const { return SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP); }

   double             NormalizeLot(const double raw) const
     {
      const double step = SymbolLotStep();
      if(step <= 0.0) return raw;
      double v = MathFloor(raw / step) * step;
      v = MathMax(v, SymbolMinLot());
      v = MathMin(v, SymbolMaxLot());
      return NormalizeDouble(v, 2);
     }

   datetime           DateOnly(const datetime t) const
     {
      MqlDateTime mt;
      TimeToStruct(t, mt);
      mt.hour = 0; mt.min = 0; mt.sec = 0;
      return StructToTime(mt);
     }

   void               ResetSessionIfNeeded()
     {
      const datetime today = DateOnly(TimeCurrent());
      if(m_session_date != today)
        {
         m_session_date         = today;
         m_session_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
        }
     }

public:
                     CRiskManager(void)
                       : m_symbol(""),
                         m_magic(0),
                         m_comment("APS_MTF"),
                         m_risk_pct(1.0),
                         m_sl_atr_mult(1.5),
                         m_tp_rr(2.0),
                         m_trail_start_rr(1.0),
                         m_max_daily_loss_pct(3.0),
                         m_max_consec_losses(4),
                         m_atr_handle(INVALID_HANDLE),
                         m_session_start_equity(0.0),
                         m_session_date(0),
                         m_consec_losses(0),
                         m_lockout_until_date(0),
                         m_atr_tf(PERIOD_M5),
                         m_atr_period(14) {}

                    ~CRiskManager(void)
     {
      if(m_atr_handle != INVALID_HANDLE)
         IndicatorRelease(m_atr_handle);
     }

   bool              Init(const string symbol, const long magic, const string comment,
                          const double risk_pct, const double sl_atr_mult,
                          const double tp_rr,    const double trail_start_rr,
                          const double max_daily_loss_pct, const int max_consec_losses,
                          const ENUM_TIMEFRAMES atr_tf, const int atr_period)
     {
      m_symbol             = symbol;
      m_magic              = magic;
      m_comment            = comment;
      m_risk_pct           = risk_pct;
      m_sl_atr_mult        = sl_atr_mult;
      m_tp_rr              = tp_rr;
      m_trail_start_rr     = trail_start_rr;
      m_max_daily_loss_pct = max_daily_loss_pct;
      m_max_consec_losses  = max_consec_losses;
      m_atr_tf             = atr_tf;
      m_atr_period         = MathMax(2, atr_period);
      m_trade.SetExpertMagicNumber((ulong)magic);
      m_trade.SetTypeFilling(ORDER_FILLING_FOK);
      m_trade.SetMarginMode();
      if(m_atr_handle != INVALID_HANDLE)
         IndicatorRelease(m_atr_handle);
      m_atr_handle = iATR(symbol, m_atr_tf, m_atr_period);
      ResetSessionIfNeeded();
      return (m_atr_handle != INVALID_HANDLE);
     }

   double            CurrentATR()
     {
      double buf[1];
      if(CopyBuffer(m_atr_handle, 0, 1, 1, buf) != 1)
         return 0.0;
      return buf[0];
     }

   //+----------------------------------------------------------------+
   //| Compute lot so that (sl_distance * pip_value) ~= risk_amount.  |
   //+----------------------------------------------------------------+
   double            ComputeLot(const double sl_distance_price)
     {
      if(sl_distance_price <= 0.0)
         return 0.0;
      const double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
      const double risk_money = equity * (m_risk_pct / 100.0);

      // Convert price-distance to monetary loss per 1 lot.
      const double tick_size  = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      const double tick_value = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
      if(tick_size <= 0.0 || tick_value <= 0.0)
         return 0.0;
      const double loss_per_lot = (sl_distance_price / tick_size) * tick_value;
      if(loss_per_lot <= 0.0)
         return 0.0;
      const double raw_lot = risk_money / loss_per_lot;
      return NormalizeLot(raw_lot);
     }

   //+----------------------------------------------------------------+
   //| Pre-trade circuit breakers.                                    |
   //+----------------------------------------------------------------+
   bool              CanOpenNew()
     {
      ResetSessionIfNeeded();
      if(m_lockout_until_date > 0 && DateOnly(TimeCurrent()) < m_lockout_until_date)
         return false;
      if(m_session_start_equity > 0.0)
        {
         const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
         const double dd_pct = 100.0 * (m_session_start_equity - equity) / m_session_start_equity;
         if(dd_pct >= m_max_daily_loss_pct)
            return false;
        }
      return true;
     }

   //+----------------------------------------------------------------+
   //| Open a market order with ATR-based SL/TP.                      |
   //+----------------------------------------------------------------+
   bool              OpenPosition(const bool is_long)
     {
      if(!CanOpenNew())
         return false;
      const double atr = CurrentATR();
      if(atr <= 0.0)
         return false;
      const double sl_distance = atr * m_sl_atr_mult;
      const double tp_distance = sl_distance * m_tp_rr;
      const double lot = ComputeLot(sl_distance);
      if(lot <= 0.0)
         return false;

      const double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      const double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      const int    dig = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      double price, sl, tp;
      if(is_long)
        {
         price = ask;
         sl = NormalizeDouble(price - sl_distance, dig);
         tp = NormalizeDouble(price + tp_distance, dig);
         return m_trade.Buy(lot, m_symbol, price, sl, tp, m_comment);
        }
      else
        {
         price = bid;
         sl = NormalizeDouble(price + sl_distance, dig);
         tp = NormalizeDouble(price - tp_distance, dig);
         return m_trade.Sell(lot, m_symbol, price, sl, tp, m_comment);
        }
     }

   //+----------------------------------------------------------------+
   //| True if this EA already has an open position on the symbol.   |
   //+----------------------------------------------------------------+
   bool              HasOpenPosition() const
     {
      const int total = PositionsTotal();
      for(int i=0; i<total; i++)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
         return true;
        }
      return false;
     }

   //+----------------------------------------------------------------+
   //| Read this EA's open-position snapshot. Returns false when flat.|
   //| `type_out` is "BUY"/"SELL", `volume_out` is in lots,           |
   //| `pl_out` includes swap + commission.                           |
   //+----------------------------------------------------------------+
   bool              PositionSnapshot(string &type_out,
                                      double &volume_out,
                                      double &pl_out) const
     {
      const int total = PositionsTotal();
      for(int i=0; i<total; i++)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
         const long type = PositionGetInteger(POSITION_TYPE);
         type_out   = (type == POSITION_TYPE_BUY) ? "BUY" : "SELL";
         volume_out = PositionGetDouble(POSITION_VOLUME);
         pl_out     = PositionGetDouble(POSITION_PROFIT)
                    + PositionGetDouble(POSITION_SWAP);
         return true;
        }
      type_out   = "";
      volume_out = 0.0;
      pl_out     = 0.0;
      return false;
     }

   //+----------------------------------------------------------------+
   //| Close all our positions on the symbol. Streak tracking happens |
   //| in OnDealClosed() (driven by OnTradeTransaction).              |
   //+----------------------------------------------------------------+
   void              CloseAll(const string reason="")
     {
      const int total = PositionsTotal();
      for(int i=total-1; i>=0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
         if(!m_trade.PositionClose(ticket))
            PrintFormat("[RiskManager] Close failed for #%I64u (%s)", ticket, reason);
        }
     }

   //+----------------------------------------------------------------+
   //| Update trailing stops on open positions.                        |
   //+----------------------------------------------------------------+
   void              ManageTrailing()
     {
      const int total = PositionsTotal();
      for(int i=0; i<total; i++)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_magic) continue;

         const long   type  = PositionGetInteger(POSITION_TYPE);
         const double open  = PositionGetDouble(POSITION_PRICE_OPEN);
         const double sl    = PositionGetDouble(POSITION_SL);
         const double tp    = PositionGetDouble(POSITION_TP);
         const int    dig   = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
         const double ask   = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         const double bid   = SymbolInfoDouble(m_symbol, SYMBOL_BID);

         if(type == POSITION_TYPE_BUY)
           {
            const double sl_dist = open - sl;
            if(sl_dist <= 0.0) continue;
            const double rr = (bid - open) / sl_dist;
            if(rr < m_trail_start_rr) continue;
            // Lock-in: trail SL at (current - sl_dist) but never below open.
            const double new_sl = NormalizeDouble(MathMax(open, bid - sl_dist), dig);
            if(new_sl > sl + _Point)
               m_trade.PositionModify(ticket, new_sl, tp);
           }
         else if(type == POSITION_TYPE_SELL)
           {
            const double sl_dist = sl - open;
            if(sl_dist <= 0.0) continue;
            const double rr = (open - ask) / sl_dist;
            if(rr < m_trail_start_rr) continue;
            const double new_sl = NormalizeDouble(MathMin(open, ask + sl_dist), dig);
            if(new_sl < sl - _Point || sl == 0.0)
               m_trade.PositionModify(ticket, new_sl, tp);
           }
        }
     }

   void              ResetConsecutiveLosses() { m_consec_losses = 0; }

   //+----------------------------------------------------------------+
   //| Record a closed deal's P/L (called from OnTradeTransaction).   |
   //| Updates the consecutive-loss counter and lockout window.       |
   //+----------------------------------------------------------------+
   void              OnDealClosed(const double profit)
     {
      if(profit < 0.0) m_consec_losses++;
      else             m_consec_losses = 0;
      if(m_consec_losses >= m_max_consec_losses)
        {
         m_lockout_until_date = DateOnly(TimeCurrent()) + 86400;
         PrintFormat("[RiskManager] Consec-losses lockout until %s",
                     TimeToString(m_lockout_until_date));
        }
     }

   long              Magic() const { return m_magic; }
  };

#endif // __APS_MTF_RISK_MANAGER_MQH__
