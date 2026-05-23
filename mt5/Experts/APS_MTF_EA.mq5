//+------------------------------------------------------------------+
//|                                                   APS_MTF_EA.mq5 |
//|  APS pressure + MTF (Stoch RSI / RCI / MACD) scoring EA          |
//|  Target: Japanese stocks via MT5 (broker-dependent).             |
//|  Timeframes:  M5 (entry) / H1 (mid) / D1 (upper)                 |
//+------------------------------------------------------------------+
#property copyright "investment-dashboard"
#property version   "1.00"
#property strict

#include <APS_MTF/APS.mqh>
#include <APS_MTF/MTFSignals.mqh>
#include <APS_MTF/Scoring.mqh>
#include <APS_MTF/RiskManager.mqh>
#include <APS_MTF/SessionFilter.mqh>

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
input group "=== General ==="
input long              InpMagicNumber       = 20260523;
input string            InpComment           = "APS_MTF";

input group "=== Timeframes ==="
input ENUM_TIMEFRAMES   InpTfLower           = PERIOD_M5;
input ENUM_TIMEFRAMES   InpTfMiddle          = PERIOD_H1;
input ENUM_TIMEFRAMES   InpTfUpper           = PERIOD_D1;

input group "=== APS ==="
input int               InpApsLookback       = 20;
input int               InpApsDivLookback    = 30;
input bool              InpApsUseRealVolume  = false;

input group "=== Stochastic RSI ==="
input int               InpSrsiRsiPeriod     = 14;
input int               InpSrsiStochPeriod   = 14;
input int               InpSrsiSmoothK       = 3;
input int               InpSrsiSmoothD       = 3;

input group "=== RCI ==="
input int               InpRciShort          = 9;
input int               InpRciLong           = 26;

input group "=== MACD ==="
input int               InpMacdFast          = 12;
input int               InpMacdSlow          = 26;
input int               InpMacdSignal        = 9;

input group "=== Scoring ==="
input double            InpLongThreshold     = 10.0;
input double            InpShortThreshold    = -10.0;
input double            InpOppositeExitScore = 8.0;

input group "=== Risk ==="
input double            InpRiskPct           = 1.0;
input double            InpSlAtrMult         = 1.5;
input double            InpTpRR              = 2.0;
input double            InpTrailStartRR      = 1.0;
input double            InpMaxDailyLossPct   = 3.0;
input int               InpMaxConsecLosses   = 4;
input int               InpAtrPeriod         = 14;

input group "=== Session (JP stocks) ==="
input bool              InpUseSessionFilter  = true;
input int               InpJstOffsetMinutes  = 0;
input bool              InpAllowOvernight    = false;

input group "=== Debug ==="
input bool              InpVerboseLog        = false;

//+------------------------------------------------------------------+
//| Globals                                                          |
//+------------------------------------------------------------------+
CAPS              g_aps;
CTFSignals        g_d1, g_h1, g_m5;
CScoring          g_scoring;
CRiskManager      g_risk;
CSessionFilter    g_session;

datetime          g_last_bar_time = 0;   // last processed M5 bar open time

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_aps.Init(_Symbol, InpTfLower, InpApsLookback, InpApsDivLookback, InpApsUseRealVolume);

   if(!g_m5.Init(_Symbol, InpTfLower,
                 InpSrsiRsiPeriod, InpSrsiStochPeriod, InpSrsiSmoothK, InpSrsiSmoothD,
                 InpRciShort, InpRciLong,
                 InpMacdFast, InpMacdSlow, InpMacdSignal))
     {
      Print("[APS_MTF] Failed to init M5 signals");
      return INIT_FAILED;
     }
   if(!g_h1.Init(_Symbol, InpTfMiddle,
                 InpSrsiRsiPeriod, InpSrsiStochPeriod, InpSrsiSmoothK, InpSrsiSmoothD,
                 InpRciShort, InpRciLong,
                 InpMacdFast, InpMacdSlow, InpMacdSignal))
     {
      Print("[APS_MTF] Failed to init H1 signals");
      return INIT_FAILED;
     }
   if(!g_d1.Init(_Symbol, InpTfUpper,
                 InpSrsiRsiPeriod, InpSrsiStochPeriod, InpSrsiSmoothK, InpSrsiSmoothD,
                 InpRciShort, InpRciLong,
                 InpMacdFast, InpMacdSlow, InpMacdSignal))
     {
      Print("[APS_MTF] Failed to init D1 signals");
      return INIT_FAILED;
     }

   g_scoring.SetWeights(CScoring::DefaultWeights());

   if(!g_risk.Init(_Symbol, InpMagicNumber, InpComment,
                   InpRiskPct, InpSlAtrMult, InpTpRR, InpTrailStartRR,
                   InpMaxDailyLossPct, InpMaxConsecLosses,
                   InpTfLower, InpAtrPeriod))
     {
      Print("[APS_MTF] Failed to init risk manager");
      return INIT_FAILED;
     }

   g_session.Init(InpUseSessionFilter, InpJstOffsetMinutes);
   g_last_bar_time = 0;

   PrintFormat("[APS_MTF] Initialized on %s. TF lower=%s mid=%s upper=%s.",
               _Symbol,
               EnumToString(InpTfLower),
               EnumToString(InpTfMiddle),
               EnumToString(InpTfUpper));
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   // CTFSignals / CRiskManager release their handles in destructors.
  }

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
bool IsNewBar()
  {
   const datetime t = iTime(_Symbol, InpTfLower, 0);
   if(t == g_last_bar_time)
      return false;
   g_last_bar_time = t;
   return true;
  }

//+------------------------------------------------------------------+
//| OnTick                                                           |
//+------------------------------------------------------------------+
void OnTick()
  {
   // Trailing runs on every tick for responsiveness.
   g_risk.ManageTrailing();

   // End-of-day flatten if overnight not allowed.
   if(!InpAllowOvernight && g_session.NeedFlattenBeforeClose(TimeCurrent()))
      g_risk.CloseAll("EOD-flatten");

   if(!IsNewBar())
      return;

   // Re-evaluate on each closed M5 bar.
   const double aps_press_raw   = g_aps.Pressure(1);
   const double aps_press_score = g_aps.PressureScore(1);
   const int    aps_div_raw     = g_aps.Divergence(1);
   const double aps_div_score   = g_aps.DivergenceScore(1);

   TFScore m5, h1, d1;
   if(!g_m5.Evaluate(m5) || !g_h1.Evaluate(h1) || !g_d1.Evaluate(d1))
     {
      if(InpVerboseLog)
         Print("[APS_MTF] Skip: indicator history not ready.");
      return;
     }

   ScoreBreakdown bd;
   const double total = g_scoring.Aggregate(aps_press_score, aps_div_score,
                                            aps_press_raw, aps_div_raw,
                                            d1, h1, m5, bd);

   if(InpVerboseLog)
      Print("[APS_MTF] ", g_scoring.Format(bd));

   const bool has_pos = g_risk.HasOpenPosition();

   // Exit on opposite-side dominance.
   if(has_pos)
     {
      const long sel_total = PositionsTotal();
      for(long i=0; i<sel_total; i++)
        {
         const ulong ticket = PositionGetTicket((int)i);
         if(ticket == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
         const long type = PositionGetInteger(POSITION_TYPE);
         if(type == POSITION_TYPE_BUY  && bd.bear_total >= InpOppositeExitScore)
           {
            g_risk.CloseAll("opposite-signal");
            return;
           }
         if(type == POSITION_TYPE_SELL && bd.bull_total >= InpOppositeExitScore)
           {
            g_risk.CloseAll("opposite-signal");
            return;
           }
         break;
        }
     }

   if(has_pos)
      return;

   // Entry gating: session + risk circuit breakers.
   if(!g_session.CanEnter(TimeCurrent()))
      return;
   if(!g_risk.CanOpenNew())
      return;

   if(total >= InpLongThreshold)
     {
      if(g_risk.OpenPosition(true) && InpVerboseLog)
         PrintFormat("[APS_MTF] LONG opened. score=%.2f", total);
     }
   else if(total <= InpShortThreshold)
     {
      if(g_risk.OpenPosition(false) && InpVerboseLog)
         PrintFormat("[APS_MTF] SHORT opened. score=%.2f", total);
     }
  }

//+------------------------------------------------------------------+
//| OnTradeTransaction: track closed deals (both EA- and broker-     |
//| initiated) for the consecutive-loss circuit breaker.             |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   const ulong deal_ticket = trans.deal;
   if(deal_ticket == 0)
      return;
   if(!HistoryDealSelect(deal_ticket))
      return;
   if(HistoryDealGetString(deal_ticket, DEAL_SYMBOL) != _Symbol)
      return;
   if((long)HistoryDealGetInteger(deal_ticket, DEAL_MAGIC) != InpMagicNumber)
      return;
   if(HistoryDealGetInteger(deal_ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT)
      return;
   const double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT)
                       + HistoryDealGetDouble(deal_ticket, DEAL_SWAP)
                       + HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
   g_risk.OnDealClosed(profit);
  }
//+------------------------------------------------------------------+
