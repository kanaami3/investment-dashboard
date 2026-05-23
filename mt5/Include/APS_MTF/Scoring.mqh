//+------------------------------------------------------------------+
//|                                                     Scoring.mqh  |
//|  Weighted aggregation across APS + MTF.                          |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_SCORING_MQH__
#define __APS_MTF_SCORING_MQH__

#include "APS.mqh"
#include "MTFSignals.mqh"

//+------------------------------------------------------------------+
//| Per-axis weights.                                                |
//+------------------------------------------------------------------+
struct ScoreWeights
  {
   double w_aps_pressure;
   double w_aps_divergence;
   double w_d1_srsi, w_d1_rci, w_d1_macd;
   double w_h1_srsi, w_h1_rci, w_h1_macd;
   double w_m5_srsi, w_m5_rci, w_m5_macd;
  };

//+------------------------------------------------------------------+
//| Detailed score breakdown (for logging / dashboards).             |
//+------------------------------------------------------------------+
struct ScoreBreakdown
  {
   double aps_pressure_raw;
   double aps_pressure_score;
   int    aps_div_raw;
   double aps_div_score;

   TFScore tf_d1;
   TFScore tf_h1;
   TFScore tf_m5;

   double total;
   double bull_total;   // sum of positive contributions
   double bear_total;   // sum of negative contributions (abs)
  };

class CScoring
  {
private:
   ScoreWeights       m_w;

   double            Apply(double raw, double w, ScoreBreakdown &b) const
     {
      const double contrib = raw * w;
      if(contrib > 0.0) b.bull_total += contrib;
      else if(contrib < 0.0) b.bear_total += -contrib;
      return contrib;
     }

public:
   void              SetWeights(const ScoreWeights &w) { m_w = w; }

   //+----------------------------------------------------------------+
   //| Default weights matching the spec.                              |
   //+----------------------------------------------------------------+
   static ScoreWeights DefaultWeights()
     {
      ScoreWeights w;
      w.w_aps_pressure   = 2.5;
      w.w_aps_divergence = 3.0;
      w.w_d1_srsi = 1.0; w.w_d1_rci = 1.0; w.w_d1_macd = 1.5;
      w.w_h1_srsi = 1.5; w.w_h1_rci = 1.5; w.w_h1_macd = 2.0;
      w.w_m5_srsi = 2.0; w.w_m5_rci = 2.0; w.w_m5_macd = 1.0;
      return w;
     }

   //+----------------------------------------------------------------+
   //| Aggregate APS + per-TF scores into a single signed score.      |
   //+----------------------------------------------------------------+
   double            Aggregate(const double aps_press_score,
                               const double aps_div_score,
                               const double aps_press_raw,
                               const int    aps_div_raw,
                               const TFScore &d1,
                               const TFScore &h1,
                               const TFScore &m5,
                               ScoreBreakdown &b) const
     {
      b.aps_pressure_raw   = aps_press_raw;
      b.aps_pressure_score = aps_press_score;
      b.aps_div_raw        = aps_div_raw;
      b.aps_div_score      = aps_div_score;
      b.tf_d1 = d1;
      b.tf_h1 = h1;
      b.tf_m5 = m5;
      b.bull_total = 0.0;
      b.bear_total = 0.0;

      double total = 0.0;
      total += Apply(aps_press_score, m_w.w_aps_pressure,   b);
      total += Apply(aps_div_score,   m_w.w_aps_divergence, b);

      total += Apply(d1.srsi, m_w.w_d1_srsi, b);
      total += Apply(d1.rci,  m_w.w_d1_rci,  b);
      total += Apply(d1.macd, m_w.w_d1_macd, b);

      total += Apply(h1.srsi, m_w.w_h1_srsi, b);
      total += Apply(h1.rci,  m_w.w_h1_rci,  b);
      total += Apply(h1.macd, m_w.w_h1_macd, b);

      total += Apply(m5.srsi, m_w.w_m5_srsi, b);
      total += Apply(m5.rci,  m_w.w_m5_rci,  b);
      total += Apply(m5.macd, m_w.w_m5_macd, b);

      b.total = total;
      return total;
     }

   //+----------------------------------------------------------------+
   //| Pretty-print the breakdown (used when VerboseLog is on).       |
   //+----------------------------------------------------------------+
   string            Format(const ScoreBreakdown &b) const
     {
      string s = StringFormat("APS press=%.2f(raw=%.3f) div=%.0f(raw=%d)  ",
                              b.aps_pressure_score, b.aps_pressure_raw,
                              b.aps_div_score, b.aps_div_raw);
      s += StringFormat("D1[srsi=%.1f rci=%.1f macd=%.1f] ",
                        b.tf_d1.srsi, b.tf_d1.rci, b.tf_d1.macd);
      s += StringFormat("H1[srsi=%.1f rci=%.1f macd=%.1f] ",
                        b.tf_h1.srsi, b.tf_h1.rci, b.tf_h1.macd);
      s += StringFormat("M5[srsi=%.1f rci=%.1f macd=%.1f] ",
                        b.tf_m5.srsi, b.tf_m5.rci, b.tf_m5.macd);
      s += StringFormat("=> total=%.2f (bull=%.2f bear=%.2f)",
                        b.total, b.bull_total, b.bear_total);
      return s;
     }
  };

#endif // __APS_MTF_SCORING_MQH__
