//+------------------------------------------------------------------+
//|                                                    StochRSI.mqh  |
//|  Stochastic RSI                                                  |
//|    1) RSI(rsi_period) on Close                                   |
//|    2) Stoch of RSI over stoch_period                             |
//|    3) %K = SMA(raw_stoch, smooth_k)                              |
//|       %D = SMA(%K,          smooth_d)                            |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_STOCHRSI_MQH__
#define __APS_MTF_STOCHRSI_MQH__

class CStochRSI
  {
private:
   string             m_symbol;
   ENUM_TIMEFRAMES    m_tf;
   int                m_rsi_period;
   int                m_stoch_period;
   int                m_smooth_k;
   int                m_smooth_d;
   int                m_rsi_handle;

   bool              EnsureHandle()
     {
      if(m_rsi_handle != INVALID_HANDLE)
         return true;
      m_rsi_handle = iRSI(m_symbol, m_tf, m_rsi_period, PRICE_CLOSE);
      return (m_rsi_handle != INVALID_HANDLE);
     }

   //+----------------------------------------------------------------+
   //| Pull a window of RSI values into rsi[] (index 0 = newest bar).  |
   //| start_shift identifies the oldest bar to return is              |
   //|   start_shift + count - 1.                                     |
   //+----------------------------------------------------------------+
   bool              CopyRSI(const int start_shift, const int count, double &rsi[]) const
     {
      ArraySetAsSeries(rsi, true);
      if(ArrayResize(rsi, count) != count)
         return false;
      const int copied = CopyBuffer(m_rsi_handle, 0, start_shift, count, rsi);
      return (copied == count);
     }

public:
                     CStochRSI(void)
                       : m_symbol(""),
                         m_tf(PERIOD_CURRENT),
                         m_rsi_period(14),
                         m_stoch_period(14),
                         m_smooth_k(3),
                         m_smooth_d(3),
                         m_rsi_handle(INVALID_HANDLE) {}

                    ~CStochRSI(void)
     {
      if(m_rsi_handle != INVALID_HANDLE)
         IndicatorRelease(m_rsi_handle);
     }

   bool              Init(const string symbol,
                          const ENUM_TIMEFRAMES tf,
                          const int rsi_period,
                          const int stoch_period,
                          const int smooth_k,
                          const int smooth_d)
     {
      m_symbol       = symbol;
      m_tf           = tf;
      m_rsi_period   = MathMax(2, rsi_period);
      m_stoch_period = MathMax(2, stoch_period);
      m_smooth_k     = MathMax(1, smooth_k);
      m_smooth_d     = MathMax(1, smooth_d);
      if(m_rsi_handle != INVALID_HANDLE)
        {
         IndicatorRelease(m_rsi_handle);
         m_rsi_handle = INVALID_HANDLE;
        }
      return EnsureHandle();
     }

   //+----------------------------------------------------------------+
   //| Compute K and D at given shift (0 = current forming bar).      |
   //| Returns false if not enough history.                            |
   //+----------------------------------------------------------------+
   bool              Compute(const int shift, double &k_out, double &d_out)
     {
      if(!EnsureHandle())
         return false;

      // To compute %D at "shift" we need smooth_d values of %K, each of
      // which needs smooth_k values of raw stochastic, each of which
      // needs stoch_period values of RSI.
      const int raw_count = m_smooth_k + m_smooth_d - 1;       // K + D smoothing depth
      const int needed    = m_stoch_period + raw_count - 1;    // total RSI samples back
      double rsi[];
      if(!CopyRSI(shift, needed, rsi))
         return false;

      // rsi[] is series-indexed: rsi[0] = newest at given shift.
      // Compute raw stochastic for the most recent (smooth_k + smooth_d - 1) bars.
      double raw[];
      ArrayResize(raw, raw_count);
      for(int r=0; r<raw_count; r++)
        {
         // window for raw[r] uses RSI[r .. r+stoch_period-1]
         double hi = rsi[r], lo = rsi[r];
         for(int j=0; j<m_stoch_period; j++)
           {
            const double v = rsi[r + j];
            if(v > hi) hi = v;
            if(v < lo) lo = v;
           }
         const double rng = hi - lo;
         raw[r] = (rng > 0.0) ? (100.0 * (rsi[r] - lo) / rng) : 50.0;
        }

      // %K = SMA(raw, smooth_k) over the latest smooth_d values
      double k_series[];
      ArrayResize(k_series, m_smooth_d);
      for(int kpos=0; kpos<m_smooth_d; kpos++)
        {
         double sum = 0.0;
         for(int j=0; j<m_smooth_k; j++)
            sum += raw[kpos + j];
         k_series[kpos] = sum / (double)m_smooth_k;
        }

      // %D = SMA(%K, smooth_d) for the current shift
      double sum_d = 0.0;
      for(int j=0; j<m_smooth_d; j++)
         sum_d += k_series[j];

      k_out = k_series[0];
      d_out = sum_d / (double)m_smooth_d;
      return true;
     }
  };

#endif // __APS_MTF_STOCHRSI_MQH__
