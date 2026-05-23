//+------------------------------------------------------------------+
//|                                                   CsvLogger.mqh  |
//|  Append per-bar score breakdown to a CSV file for offline        |
//|  tuning / inspection.                                            |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_CSV_LOGGER_MQH__
#define __APS_MTF_CSV_LOGGER_MQH__

#include "Scoring.mqh"

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
                "action","price");
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

   void              Log(const datetime t, const string symbol, const string tf,
                         const ScoreBreakdown &b,
                         const string action, const double price)
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
                action,
                DoubleToString(price, 5));
      FileClose(h);
     }
  };

#endif // __APS_MTF_CSV_LOGGER_MQH__
