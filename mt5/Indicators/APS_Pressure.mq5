//+------------------------------------------------------------------+
//|                                                APS_Pressure.mq5  |
//|  Visualizes APS pressure as a sub-window histogram.              |
//|  Range: -1.0 .. +1.0.                                            |
//+------------------------------------------------------------------+
#property copyright "investment-dashboard"
#property version   "1.00"
#property strict
#property indicator_separate_window
#property indicator_buffers 2
#property indicator_plots   2

#property indicator_label1  "APS Pressure"
#property indicator_type1   DRAW_HISTOGRAM
#property indicator_color1  clrDodgerBlue
#property indicator_width1  2

#property indicator_label2  "Zero"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrGray
#property indicator_style2  STYLE_DOT

input int  InpLookback        = 20;
input bool InpUseRealVolume   = false;

double BufPressure[];
double BufZero[];

//+------------------------------------------------------------------+
int OnInit()
  {
   SetIndexBuffer(0, BufPressure, INDICATOR_DATA);
   SetIndexBuffer(1, BufZero,     INDICATOR_DATA);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("APS Pressure (%d)", InpLookback));
   IndicatorSetInteger(INDICATOR_DIGITS, 3);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Compute APS Pressure for bar index 'pos' using historical arrays. |
//+------------------------------------------------------------------+
double ComputeAt(const int pos,
                 const double &high[],  const double &low[],
                 const double &close[],
                 const long   &tickv[], const long   &realv[],
                 const bool   use_real)
  {
   if(pos - InpLookback + 1 < 0) return 0.0;
   double posv = 0.0, negv = 0.0;
   for(int i=pos - InpLookback + 1; i<=pos; i++)
     {
      const double h = high[i];
      const double l = low[i];
      const double c = close[i];
      const long   v = use_real ? realv[i] : tickv[i];
      if(h <= l || v <= 0) continue;
      const double mfm = ((c - l) - (h - c)) / (h - l);
      const double mfv = mfm * (double)v;
      if(mfv > 0.0) posv += mfv;
      else          negv += -mfv;
     }
   const double tot = posv + negv;
   if(tot <= 0.0) return 0.0;
   return (posv - negv) / tot;
  }

//+------------------------------------------------------------------+
int OnCalculate(const int        rates_total,
                const int        prev_calculated,
                const datetime  &time[],
                const double    &open[],
                const double    &high[],
                const double    &low[],
                const double    &close[],
                const long      &tick_volume[],
                const long      &real_volume[],
                const int       &spread[])
  {
   int start = MathMax(prev_calculated - 1, InpLookback);
   for(int i=start; i<rates_total; i++)
     {
      BufZero[i]     = 0.0;
      BufPressure[i] = ComputeAt(i, high, low, close,
                                 tick_volume, real_volume, InpUseRealVolume);
     }
   return rates_total;
  }
//+------------------------------------------------------------------+
