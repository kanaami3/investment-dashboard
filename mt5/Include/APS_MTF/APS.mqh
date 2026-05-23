//+------------------------------------------------------------------+
//|                                                          APS.mqh |
//|  APS (Absorption Pressure System)                                |
//|  - Pressure: directional money-flow-volume ratio (-1..+1)        |
//|  - Divergence: bullish (+1) / none (0) / bearish (-1)            |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_APS_MQH__
#define __APS_MTF_APS_MQH__

class CAPS
  {
private:
   string             m_symbol;
   ENUM_TIMEFRAMES    m_tf;
   int                m_lookback;
   int                m_div_lookback;
   bool               m_use_real_volume;

   long               BarVolume(int shift) const
     {
      if(m_use_real_volume)
         return (long)iRealVolume(m_symbol, m_tf, shift);
      return (long)iTickVolume(m_symbol, m_tf, shift);
     }

public:
                     CAPS(void)
                       : m_symbol(""),
                         m_tf(PERIOD_CURRENT),
                         m_lookback(20),
                         m_div_lookback(30),
                         m_use_real_volume(false) {}

   void              Init(const string symbol,
                          const ENUM_TIMEFRAMES tf,
                          const int lookback,
                          const int div_lookback,
                          const bool use_real_volume)
     {
      m_symbol          = symbol;
      m_tf              = tf;
      m_lookback        = MathMax(5, lookback);
      m_div_lookback    = MathMax(10, div_lookback);
      m_use_real_volume = use_real_volume;
     }

   //+----------------------------------------------------------------+
   //| Pressure value at given shift (default 1 = last closed bar)    |
   //+----------------------------------------------------------------+
   double            Pressure(const int shift=1) const
     {
      double pos = 0.0, neg = 0.0;
      const int total_bars = Bars(m_symbol, m_tf);
      const int end = shift + m_lookback;
      if(end >= total_bars)
         return 0.0;

      for(int i=shift; i<end; i++)
        {
         const double h = iHigh(m_symbol, m_tf, i);
         const double l = iLow(m_symbol, m_tf, i);
         const double c = iClose(m_symbol, m_tf, i);
         const long   v = BarVolume(i);
         if(h <= l || v <= 0)
            continue;
         const double mfm = ((c - l) - (h - c)) / (h - l);
         const double mfv = mfm * (double)v;
         if(mfv > 0.0) pos += mfv;
         else          neg += -mfv;
        }
      const double tot = pos + neg;
      if(tot <= 0.0)
         return 0.0;
      return (pos - neg) / tot;
     }

   //+----------------------------------------------------------------+
   //| Divergence between price extrema and APS Pressure.             |
   //|   +1: bullish (price LL, APS HL)                               |
   //|   -1: bearish (price HH, APS LH)                               |
   //|    0: none                                                      |
   //+----------------------------------------------------------------+
   int               Divergence(const int shift=1) const
     {
      const int total_bars = Bars(m_symbol, m_tf);
      if(shift + m_div_lookback + m_lookback >= total_bars)
         return 0;

      const int half = m_div_lookback / 2;
      const int idx_low_recent  = iLowest(m_symbol, m_tf, MODE_LOW,  half, shift);
      const int idx_low_prev    = iLowest(m_symbol, m_tf, MODE_LOW,  half, shift + half);
      const int idx_high_recent = iHighest(m_symbol, m_tf, MODE_HIGH, half, shift);
      const int idx_high_prev   = iHighest(m_symbol, m_tf, MODE_HIGH, half, shift + half);

      if(idx_low_recent < 0 || idx_low_prev < 0 ||
         idx_high_recent < 0 || idx_high_prev < 0)
         return 0;

      const double l_recent = iLow(m_symbol, m_tf, idx_low_recent);
      const double l_prev   = iLow(m_symbol, m_tf, idx_low_prev);
      const double aps_l_recent = Pressure(idx_low_recent);
      const double aps_l_prev   = Pressure(idx_low_prev);

      const double h_recent = iHigh(m_symbol, m_tf, idx_high_recent);
      const double h_prev   = iHigh(m_symbol, m_tf, idx_high_prev);
      const double aps_h_recent = Pressure(idx_high_recent);
      const double aps_h_prev   = Pressure(idx_high_prev);

      if(l_recent < l_prev && aps_l_recent > aps_l_prev)
         return +1;
      if(h_recent > h_prev && aps_h_recent < aps_h_prev)
         return -1;
      return 0;
     }

   //+----------------------------------------------------------------+
   //| Convert Pressure to score (-2..+2)                              |
   //+----------------------------------------------------------------+
   double            PressureScore(const int shift=1) const
     {
      const double p = Pressure(shift);
      if(p >=  0.6) return  2.0;
      if(p >=  0.2) return  1.0;
      if(p <= -0.6) return -2.0;
      if(p <= -0.2) return -1.0;
      return 0.0;
     }

   //+----------------------------------------------------------------+
   //| Divergence score (-2 / 0 / +2)                                  |
   //+----------------------------------------------------------------+
   double            DivergenceScore(const int shift=1) const
     {
      return 2.0 * (double)Divergence(shift);
     }
  };

#endif // __APS_MTF_APS_MQH__
