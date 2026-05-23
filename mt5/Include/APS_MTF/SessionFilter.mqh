//+------------------------------------------------------------------+
//|                                              SessionFilter.mqh   |
//|  Japanese stock-market session filter (JST).                     |
//|                                                                  |
//|  Morning session : 09:00 - 11:30 JST                             |
//|  Afternoon       : 12:30 - 15:00 JST                             |
//|                                                                  |
//|  Entries allowed:                                                |
//|    - 5 minutes after each open                                   |
//|    - up to 15 minutes before each close                          |
//|  New-position cutoff: 30 minutes before 15:00 (configurable).    |
//+------------------------------------------------------------------+
#ifndef __APS_MTF_SESSION_FILTER_MQH__
#define __APS_MTF_SESSION_FILTER_MQH__

class CSessionFilter
  {
private:
   bool              m_enabled;
   int               m_jst_offset_minutes;  // server time + offset = JST
   int               m_entry_open_delay;    // minutes after open before entries
   int               m_entry_close_buffer;  // minutes before close to stop entries
   int               m_no_new_before_close; // additional cutoff before 15:00

   int               JstMinutes(const datetime t) const
     {
      const datetime jst_t = t + (datetime)(m_jst_offset_minutes * 60);
      MqlDateTime mt;
      TimeToStruct(jst_t, mt);
      return mt.hour * 60 + mt.min;
     }

   bool              IsWeekday(const datetime t) const
     {
      const datetime jst_t = t + (datetime)(m_jst_offset_minutes * 60);
      MqlDateTime mt;
      TimeToStruct(jst_t, mt);
      // 0=Sun, 6=Sat
      return (mt.day_of_week >= 1 && mt.day_of_week <= 5);
     }

public:
                     CSessionFilter(void)
                       : m_enabled(true),
                         m_jst_offset_minutes(0),
                         m_entry_open_delay(5),
                         m_entry_close_buffer(15),
                         m_no_new_before_close(30) {}

   void              Init(const bool enabled,
                          const int jst_offset_minutes,
                          const int entry_open_delay   = 5,
                          const int entry_close_buffer = 15,
                          const int no_new_before_close = 30)
     {
      m_enabled             = enabled;
      m_jst_offset_minutes  = jst_offset_minutes;
      m_entry_open_delay    = entry_open_delay;
      m_entry_close_buffer  = entry_close_buffer;
      m_no_new_before_close = no_new_before_close;
     }

   //+----------------------------------------------------------------+
   //| Whether we are currently inside any trading session.           |
   //+----------------------------------------------------------------+
   bool              InSession(const datetime t) const
     {
      if(!m_enabled) return true;
      if(!IsWeekday(t)) return false;
      const int m = JstMinutes(t);
      const bool morning   = (m >= 9*60   && m <= 11*60 + 30);
      const bool afternoon = (m >= 12*60+30 && m <= 15*60);
      return morning || afternoon;
     }

   //+----------------------------------------------------------------+
   //| Whether new entries are allowed right now.                     |
   //+----------------------------------------------------------------+
   bool              CanEnter(const datetime t) const
     {
      if(!m_enabled) return true;
      if(!IsWeekday(t)) return false;
      const int m = JstMinutes(t);

      // Morning entry window
      const bool morning_ok = (m >= 9*60 + m_entry_open_delay) &&
                              (m <= 11*60 + 30 - m_entry_close_buffer);
      // Afternoon entry window
      const bool afternoon_ok = (m >= 12*60 + 30 + m_entry_open_delay) &&
                                (m <= 15*60 - m_entry_close_buffer);
      // Final cutoff
      const bool not_too_late = m <= (15*60 - m_no_new_before_close);

      return (morning_ok || afternoon_ok) && not_too_late;
     }

   //+----------------------------------------------------------------+
   //| Whether we should force-flatten by end of session today.       |
   //+----------------------------------------------------------------+
   bool              NeedFlattenBeforeClose(const datetime t,
                                            const int minutes_before=2) const
     {
      if(!m_enabled) return false;
      if(!IsWeekday(t)) return false;
      const int m = JstMinutes(t);
      return (m >= 15*60 - minutes_before && m <= 15*60 + 5);
     }
  };

#endif // __APS_MTF_SESSION_FILTER_MQH__
