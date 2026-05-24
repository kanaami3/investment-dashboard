//+------------------------------------------------------------------+
//|                                                   CsvLogger.mqh  |
//|  Append per-bar score breakdown + execution context to a CSV     |
//|  file for offline tuning / post-mortem.                          |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_CSV_LOGGER_MQH__
#define __APS_MTF_CSV_LOGGER_MQH__

#include "Scoring.mqh"

//+------------------------------------------------------------------+
//| Execution context captured at decision time.                     |
//|                                                                  |
//| Filled by the EA before each Log() call so the CSV row alone     |
//| is enough to reconstruct *why* an action was taken.              |
//+------------------------------------------------------------------+
struct LogContext
  {
   double  atr;             // ATR(period) on the lower TF
   double  spread_points;   // (ask-bid)/point at decision time
   double  equity;
   double  balance;
   double  long_thr;        // current InpLongThreshold
   double  short_thr;       // current InpShortThreshold
   string  block_reason;    // "" | "session" | "risk" | "session+risk"
   string  pos_type;        // "" | "BUY" | "SELL"
   double  pos_volume;      // 0 if flat
   double  pos_pl;          // unrealized P/L incl. swap+commission (0 if flat)
  };

class CCsvLogger
  {
private:
   bool   m_enabled;
   string m_path;
   bool   m_header_written;

   void   WriteHeaderIfNeeded()
     {
      if(m_header_written) return;
      int h = FileOpen(m_path, FILE_READ | FILE_CSV | FILE_ANSI);
      const bool already = (h != INVALID_HANDLE);
      if(already)
        {
         m_header_written = true;
         FileClose(h);
         return;
        }
      h = FileOpen(m_path, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
      if(h == INVALID_HANDLE) return;
      FileWrite(h,
                "time","symbol","tf",
                "aps_pressure_raw","aps_pressure_score","aps_div_raw","aps_div_score",
                "d1_srsi","d1_rci","d1_macd",
                "h1_srsi","h1_rci","h1_macd",
                "m5_srsi","m5_rci","m5_macd",
                "bull_total","bear_total","total",
                "long_thr","short_thr",
                "action","price",
                "atr","spread_points",
                "equity","balance",
                "block_reason",
                "pos_type","pos_volume","pos_pl");
      FileClose(h);
      m_header_written = true;
     }

public:
                     CCsvLogger(void)
                       : m_enabled(false), m_path(""), m_header_written(false) {}

   void              Init(const bool enabled, const string path)
     {
      m_enabled        = enabled && (StringLen(path) > 0);
      m_path           = path;
      m_header_written = false;
      if(m_enabled) WriteHeaderIfNeeded();
     }

   //+----------------------------------------------------------------+
   //| Static helper: empty context for callers that have nothing to  |
   //| report (kept for backwards-compatible call sites).             |
   //+----------------------------------------------------------------+
   static LogContext EmptyContext()
     {
      LogContext c;
      c.atr           = 0.0;
      c.spread_points = 0.0;
      c.equity        = 0.0;
      c.balance       = 0.0;
      c.long_thr      = 0.0;
      c.short_thr     = 0.0;
      c.block_reason  = "";
      c.pos_type      = "";
      c.pos_volume    = 0.0;
      c.pos_pl        = 0.0;
      return c;
     }

   void              Log(const datetime t, const string symbol, const string tf,
                         const ScoreBreakdown &b,
                         const string action, const double price,
                         const LogContext &ctx)
     {
      if(!m_enabled) return;
      int h = FileOpen(m_path, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
      if(h == INVALID_HANDLE) return;
      FileSeek(h, 0, SEEK_END);
      FileWrite(h,
                TimeToString(t, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
                symbol, tf,
                DoubleToString(b.aps_pressure_raw, 5),
                DoubleToString(b.aps_pressure_score, 2),
                IntegerToString(b.aps_div_raw),
                DoubleToString(b.aps_div_score, 2),
                DoubleToString(b.tf_d1.srsi, 2),
                DoubleToString(b.tf_d1.rci,  2),
                DoubleToString(b.tf_d1.macd, 2),
                DoubleToString(b.tf_h1.srsi, 2),
                DoubleToString(b.tf_h1.rci,  2),
                DoubleToString(b.tf_h1.macd, 2),
                DoubleToString(b.tf_m5.srsi, 2),
                DoubleToString(b.tf_m5.rci,  2),
                DoubleToString(b.tf_m5.macd, 2),
                DoubleToString(b.bull_total, 3),
                DoubleToString(b.bear_total, 3),
                DoubleToString(b.total,      3),
                DoubleToString(ctx.long_thr,  3),
                DoubleToString(ctx.short_thr, 3),
                action,
                DoubleToString(price, 5),
                DoubleToString(ctx.atr,           5),
                DoubleToString(ctx.spread_points, 1),
                DoubleToString(ctx.equity,        2),
                DoubleToString(ctx.balance,       2),
                ctx.block_reason,
                ctx.pos_type,
                DoubleToString(ctx.pos_volume, 2),
                DoubleToString(ctx.pos_pl,     2));
      FileClose(h);
     }
  };

#endif // __APS_MTF_CSV_LOGGER_MQH__
