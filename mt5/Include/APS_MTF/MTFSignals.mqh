//+------------------------------------------------------------------+
//|                                                  MTFSignals.mqh  |
//|  Per-timeframe scoring for StochRSI / RCI / MACD                 |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_MTFSIGNALS_MQH__
#define __APS_MTF_MTFSIGNALS_MQH__

#include "RCI.mqh"
#include "StochRSI.mqh"

//+------------------------------------------------------------------+
//| Score breakdown for a single timeframe.                          |
//+------------------------------------------------------------------+
struct TFScore
  {
   double            srsi;     // -2..+2
   double            rci;      // -2..+2
   double            macd;     // -2..+2
   double            srsi_k;
   double            srsi_d;
   double            rci_short;
   double            rci_long;
   double            macd_main;
   double            macd_signal;
   double            macd_hist;
   double            macd_hist_prev;
  };

//+------------------------------------------------------------------+
//| Bundles indicator handles + helpers for one timeframe.           |
//+------------------------------------------------------------------+
class CTFSignals
  {
private:
   string             m_symbol;
   ENUM_TIMEFRAMES    m_tf;

   CStochRSI          m_srsi;
   CRCI               m_rci_short;
   CRCI               m_rci_long;
   int                m_macd_handle;

   int                m_macd_fast;
   int                m_macd_slow;
   int                m_macd_signal;

   double            ScoreStochRSI(const double k, const double d,
                                   const double k_prev, const double d_prev) const
     {
      // Bullish cross in oversold
      if(k_prev <= d_prev && k > d && k < 20.0 && d < 20.0)
         return 2.0;
      // Bearish cross in overbought
      if(k_prev >= d_prev && k < d && k > 80.0 && d > 80.0)
         return -2.0;
      // Trend bias
      if(k > d && k > k_prev) return  1.0;
      if(k < d && k < k_prev) return -1.0;
      return 0.0;
     }

   double            ScoreRCI(const double r_short, const double r_long,
                              const double r_short_prev) const
     {
      // Exits from extreme zones
      if(r_short_prev <= -80.0 && r_short > -80.0) return  2.0;
      if(r_short_prev >=  80.0 && r_short <  80.0) return -2.0;
      // Sign agreement
      if(r_short > 0.0 && r_long > 0.0) return  1.0;
      if(r_short < 0.0 && r_long < 0.0) return -1.0;
      return 0.0;
     }

   double            ScoreMACD(const double main, const double sig,
                               const double hist, const double hist_prev) const
     {
      // Hist flips
      if(hist_prev <= 0.0 && hist > 0.0 && main < 0.0) return  2.0;
      if(hist_prev >= 0.0 && hist < 0.0 && main > 0.0) return -2.0;
      if(main > sig) return  1.0;
      if(main < sig) return -1.0;
      return 0.0;
     }

   bool              GetMACD(const int shift,
                             double &main_out, double &sig_out, double &hist_out) const
     {
      double m_buf[1], s_buf[1];
      if(CopyBuffer(m_macd_handle, 0, shift, 1, m_buf) != 1) return false;
      if(CopyBuffer(m_macd_handle, 1, shift, 1, s_buf) != 1) return false;
      main_out = m_buf[0];
      sig_out  = s_buf[0];
      hist_out = main_out - sig_out;
      return true;
     }

public:
                     CTFSignals(void) : m_macd_handle(INVALID_HANDLE) {}
                    ~CTFSignals(void)
     {
      if(m_macd_handle != INVALID_HANDLE)
         IndicatorRelease(m_macd_handle);
     }

   bool              Init(const string symbol,
                          const ENUM_TIMEFRAMES tf,
                          const int rsi_period, const int stoch_period,
                          const int smooth_k,   const int smooth_d,
                          const int rci_short,  const int rci_long,
                          const int macd_fast,  const int macd_slow,
                          const int macd_signal)
     {
      m_symbol = symbol;
      m_tf     = tf;

      if(!m_srsi.Init(symbol, tf, rsi_period, stoch_period, smooth_k, smooth_d))
         return false;
      m_rci_short.Init(symbol, tf, rci_short);
      m_rci_long.Init (symbol, tf, rci_long);

      m_macd_fast   = macd_fast;
      m_macd_slow   = macd_slow;
      m_macd_signal = macd_signal;
      if(m_macd_handle != INVALID_HANDLE)
        {
         IndicatorRelease(m_macd_handle);
         m_macd_handle = INVALID_HANDLE;
        }
      m_macd_handle = iMACD(symbol, tf, macd_fast, macd_slow, macd_signal, PRICE_CLOSE);
      return (m_macd_handle != INVALID_HANDLE);
     }

   //+----------------------------------------------------------------+
   //| Fill TFScore using shift=1 (last closed bar).                  |
   //+----------------------------------------------------------------+
   bool              Evaluate(TFScore &out)
     {
      double k=0, d=0, k_prev=0, d_prev=0;
      if(!m_srsi.Compute(1, k, d))         return false;
      if(!m_srsi.Compute(2, k_prev, d_prev)) return false;

      const double rs       = m_rci_short.Value(1);
      const double rs_prev  = m_rci_short.Value(2);
      const double rl       = m_rci_long.Value(1);

      double m_main=0, m_sig=0, m_hist=0;
      double m_main_p=0, m_sig_p=0, m_hist_p=0;
      if(!GetMACD(1, m_main,   m_sig,   m_hist))   return false;
      if(!GetMACD(2, m_main_p, m_sig_p, m_hist_p)) return false;

      out.srsi_k          = k;
      out.srsi_d          = d;
      out.rci_short       = rs;
      out.rci_long        = rl;
      out.macd_main       = m_main;
      out.macd_signal     = m_sig;
      out.macd_hist       = m_hist;
      out.macd_hist_prev  = m_hist_p;

      out.srsi = ScoreStochRSI(k, d, k_prev, d_prev);
      out.rci  = ScoreRCI(rs, rl, rs_prev);
      out.macd = ScoreMACD(m_main, m_sig, m_hist, m_hist_p);
      return true;
     }
  };

#endif // __APS_MTF_MTFSIGNALS_MQH__
