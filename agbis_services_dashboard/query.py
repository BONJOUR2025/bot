# query.py
# Базовый SQL из ТЗ. ВАЖНО: строка начинается с "select", без обратного слеша.

BASE_SQL = """
select 
    docs.doc_date,
    docs_order.creater_id,
    docs_order.sclad_kredit_id,
    docs.contragent_id,
    docs.doc_num,
    doc_order_services.barcode_read,
    tovars_tbl.tovar_id,
    tovars_tbl.folder_id,
    tovars_tbl.tovar_type,
    tovars_tbl.code,
    tovars_tbl.name,
    doc_order_services.kredit,
    doc_order_services.doc_order_id,
    doc_order_services.status_id,
    docs_order.doc_id,
    user_session_actions.date_beg,
    user_session_actions.date_end,
    user_session_actions.work_place_id,
    user_session.user_id,
    users.description,
    user_session_actions.barcode,
    doc_order_services.id,
    doc_order_services.kfx,
    doc_order_services.qty_kredit

from doc_order_services

inner join docs_order 
    on doc_order_services.doc_order_id = docs_order.id

inner join docs 
    on docs_order.doc_id = docs.doc_id

inner join tovars_tbl 
    on doc_order_services.tovar_id = tovars_tbl.tovar_id

inner join user_session_actions 
    on doc_order_services.id = user_session_actions.doc_order_services_id

inner join user_session 
    on user_session_actions.user_session_id = user_session.id

left join users
    on user_session.user_id = users.user_id

where 
      user_session_actions.work_place_id in 
      (1107,11017,11019,1108,11018,11020,11022,11024,1154,11028)
  and 
      tovars_tbl.folder_id in 
      (327,210289,416,210282,216,210347,210307,210320,210365,417,418,210348,210350,210349,210405,326,328,210290,210281,210268,210276,210267,215,210275,210269,210278,108401,329,330,108402,210270,210334,210337,210341,210336,210338,210340,210342,210343,210345,210346,210291,210292,210293,110409,210297,210298,210299,210283,210308,110410,110411,210309,210310,210314,210315,210316,210300,210306,210322,210323,210319,210318,210317,210326,210332,210333,210355,210358,210363,210357,210359,210361,210364,419,210280,210273,221,210272,217,210277,210366,210344,210356,210286,210274,210271,210335,210353,210279,210288,210380,210339,210399,210360,210384,210296,210266,210313,210331,210295,210287,210294,210285,210284,210325,210324,210330,210321,210329,210328,210327,210305,210312,210304,210311,210303,210302,210301,210351,210352,210382,210385,210377,210391,210394,210392,210378,210393,210388,210396,210395,210381,210390,210389,210397,210383,210386,210379,210387,110407,110421)
  AND DOC_DATE > '2023-01-01'
"""