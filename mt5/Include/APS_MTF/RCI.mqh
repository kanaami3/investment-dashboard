//+------------------------------------------------------------------+
//|                                                         RCI.mqh  |
//|  Rank Correlation Index                                          |
//|   RCI = (1 - 6*Σd² / (n*(n²-1))) * 100                           |
//|   d = price_rank - time_rank                                     |
//|  Returns value in [-100, +100].                                  |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_RCI_MQH__
#define __APS_MTF_RCI_MQH__

class CRCI
  {
private:
   string             m_symbol;
   ENUM_TIMEFRAMES    m_tf;
   int                m_period;

public:
                     CRCI(void) : m_symbol(""), m_tf(PERIOD_CURRENT), m_period(9) {}

   void              Init(const string symbol,
                          const ENUM_TIMEFRAMES tf,
                          const int period)
     {
      m_symbol = symbol;
      m_tf     = tf;
      m_period = MathMax(3, period);
     }

   int               Period() const { return m_period; }

   //+----------------------------------------------------------------+
   //| RCI value at given shift.                                       |
   //|  shift=1 => last closed bar.                                    |
   //+----------------------------------------------------------------+
   double            Value(const int shift=1) const
     {
      const int n = m_period;
      const int total_bars = Bars(m_symbol, m_tf);
      if(shift + n >= total_bars)
         return 0.0;

      double closes[];
      ArrayResize(closes, n);
      for(int i=0; i<n; i++)
         closes[i] = iClose(m_symbol, m_tf, shift + i);

      // Time rank: closes[0] (most recent) = 1, closes[n-1] = n
      // Price rank: count of closes strictly greater + 1 (ties broken
      // deterministically by giving the earlier index the higher rank).
      double sum_d2 = 0.0;
      for(int i=0; i<n; i++)
        {
         int higher = 0;
         for(int j=0; j<n; j++)
           {
            if(j == i) continue;
            if(closes[j] > closes[i])
               higher++;
            else if(closes[j] == closes[i] && j < i)
               higher++;
           }
         const int price_rank = higher + 1;
         const int time_rank  = i + 1;
         const double d = (double)(price_rank - time_rank);
         sum_d2 += d * d;
        }
      const double denom = (double)n * ((double)n * n - 1.0);
      if(denom <= 0.0)
         return 0.0;
      return (1.0 - 6.0 * sum_d2 / denom) * 100.0;
     }
  };

#endif // __APS_MTF_RCI_MQH__
