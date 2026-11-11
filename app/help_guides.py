"""Plain-language card Help. Examples explain rules, not live records."""

CARD_GUIDES = {'card-vip-vvip': {'title': 'VVIP Site: VIP and VVIP alarms',
                   'group': 'Live alarm cards',
                   'intro': 'This card focuses on active alarms affecting VIP and VVIP sites. Although '
                            'the heading says VVIP Site, the selection accepts both designations.',
                   'sections': [('Where the data comes from',
                                 ['Streamline alarm records come from the Streamline alarm database. '
                                  'The the cached Streamline alarm list query keeps Opened alarms with '
                                  'a recorded occurrence time. It keeps the latest event for each '
                                  'combination of raw site, event name, and location, while retaining '
                                  'an occurrence count.',
                                  'VIP alarm sync filters that cache using VIP/VVIP designations from '
                                  'the cached Streamline site inventory or the cached MSSQL VIP '
                                  'inventory. The MSSQL inventory uses TBL_SITE and TBL_NE for On Air, '
                                  'not-removed VIP/VVIP sites. Displayed alarms also require a matching '
                                  'the cached site inventory record.']),
                                ('What each badge means',
                                 ['Site Down uses recognized connectivity and technology-down event '
                                  'names. Main AC Failure matches main failure text. Low and High DC '
                                  'Voltage match their respective DC text. DG-On uses the event or '
                                  'additional information. Rectifier and door events use RECT Failure '
                                  'and Door Alarm. Remaining events go to Other.',
                                  'High Temperature has no separate badge here. An Opened temperature '
                                  'event can appear under Other if the site qualifies. Open the '
                                  'drilldown to inspect the actual event and additional information.']),
                                ('How the number is counted',
                                 ['Each category counts distinct site codes, not alarm rows. One site '
                                  'can appear once in Main AC Failure and once in Low DC Voltage. '
                                  'Adding all category values therefore does not give a unique total of '
                                  'affected sites.']),
                                ('Example: two sites, four alarm rows',
                                 ['Site 0460 has three Main AC Failure rows and site 1002 has one. The '
                                  'badge shows 2 sites. Clicking 2 can show four alarm rows, because '
                                  'the table explains the alarms behind the two sites.']),
                                ('Clicking a badge',
                                 ['A badge opens that alarm category; View Alarms opens the broader '
                                  'list. Site inventory supplies grade and location. Ticket references '
                                  'are enriched from the cached VIP incident list, which can retain '
                                  'Resolved incident references until Closed. A resolved ticket '
                                  'reference does not itself prove the alarm cleared.']),
                                ('If a site is missing',
                                 ['Check that the alarm is Opened, the site code resolves, the cached '
                                  'site inventory contains the site, and either inventory marks it '
                                  'VIP/VVIP. After an inventory change, allow both inventory and alarm '
                                  'jobs to finish.']),
                                ('Site Down and power alarms in everyday use',
                                 ['A Site Down badge is based on recognized outage event names, not a '
                                  'person reading the alarm note and deciding that the site sounds '
                                  'down. If a source event is outside those names, it can fall into '
                                  'another group. Always inspect the event text when a familiar site is '
                                  'absent from the category you expected.',
                                  'Main AC Failure means the alarm describes a mains power problem. It '
                                  'does not alone say that the site has stopped carrying service. A '
                                  'site running on batteries or a generator can have a mains alarm '
                                  'while remaining reachable. Low DC Voltage describes a different '
                                  'power condition and can appear at the same site.',
                                  'High DC Voltage is kept separate from Low DC Voltage. DG-On '
                                  'identifies a generator-running indication using the supported event '
                                  'or additional-information text. RECT Failure and Door Alarm follow '
                                  'their event keywords. These categories explain what the source '
                                  'reported; they do not automatically establish a verified root cause.',
                                  'Other contains remaining matched VIP/VVIP alarms. It is not an error '
                                  'bucket or a statement that those events are unimportant. A hardware '
                                  'or temperature event can be operationally important even without its '
                                  'own dedicated badge. Open Other and read the exact event rather than '
                                  'ignoring it.']),
                                ('Worked investigation from the badge to the incident',
                                 ['You receive a report that VIP site 0460 has a power problem. Open '
                                  'Main AC Failure and find 0460 in the table. Read its occurrence time '
                                  'and additional information. If three event rows share that site '
                                  'code, remember the category still contributes one site to the badge.',
                                  'Next inspect any incident reference. That reference is added from '
                                  'cached ticket data, so its status can differ from the current event '
                                  'status. A Resolved ticket alongside an Opened alarm needs '
                                  'investigation; it is not sufficient to conclude the alarm is '
                                  'cleared. Check both source records and their update times.',
                                  'Finally, compare the same site code in Mentor or RAN only if that '
                                  'view applies. Mentor requires a configured selection; RAN uses '
                                  'technology coverage and inventory. A site appearing in VIP but not '
                                  'Mentor is expected when it was never added to the Mentor list.'])],
                   'refresh_setting': 'VIP_ALARM_SYNC_INTERVAL_SECONDS'},
 'card-mentor': {'title': 'Mentor Site: selected-site monitoring',
                 'group': 'Live alarm cards',
                 'intro': 'Mentor Site is your saved list of sites to watch closely. Those sites do not '
                          'need to be VIP or VVIP.',
                 'sections': [('Choose the sites first',
                               ['Open Mentor Site and enter site inventory codes, or import a CSV using '
                                'the downloadable template. Codes are validated against the site '
                                'database. Unknown codes fail validation. Entering a POP identifier '
                                'alone does not enable POP monitoring.',
                                'Review file validation before completing the import. Keep leading '
                                'zeroes in site codes, use the template column header, and correct '
                                'rejected values instead of treating a failed file as successfully '
                                'imported.']),
                              ('Where the records come from',
                               ['The service matches the saved codes against the cached Streamline '
                                'alarm list and uses the cached site inventory for names and provinces. '
                                'It also checks active the cached active incident list records in the '
                                'Site Down category.',
                                'When a monitored site has an active Site Down incident but no Site '
                                'Down alarm, the service adds an incident-based entry. This avoids '
                                'showing OK solely because an alarm cleared while its active ticket '
                                'remains.']),
                              ('What the badges count',
                               ['The categories are Site Down, Main AC Failure, Low DC Voltage, High DC '
                                'Voltage, DG-On, RECT Failure, Door Alarm, and Other. Each counts '
                                'distinct configured sites in that category. Several alarms at one site '
                                'count once in that category; a site can appear in several '
                                'categories.']),
                              ('Example: an alarm and an incident',
                               ['You monitor 0460 and 1002. Site 0460 has two Main AC Failure alarms. '
                                'Site 1002 has an active Site Down incident but no current down alarm. '
                                'Main AC Failure shows 1 and Site Down shows 1. The alarm table can '
                                'have more rows than either site count.']),
                              ('Status and drilldown',
                               ['View Alarms shows the configured list; the per-site View action '
                                'narrows to one site. Site Down takes precedence in the configured-site '
                                'status. OK means no qualifying record was found in the current matched '
                                'caches, not that every external monitoring system has been checked.']),
                              ('What stays saved',
                               ['The selected sites survive refresh and restart when instance data is '
                                'retained. Removing a site removes it from Mentor monitoring, not the '
                                'source inventory. Alarm and incident freshness still depends on their '
                                'own background jobs.']),
                              ('Adding one site and importing many sites',
                               ['For one site, use its exact inventory code and review the validation '
                                'response before treating it as monitored. Leading zeroes are part of '
                                'the identifier. A spreadsheet converting 0460 into 460 can make the '
                                'imported value fail validation or refer to the wrong identifier.',
                                'For multiple sites, start from the available template rather than a '
                                'file with unrelated columns. Keep the expected site-code header, '
                                'remove accidental spaces, and check the file result. A completed '
                                'progress bar indicates the file-processing step has finished; review '
                                'whether the result says valid or failed before continuing.',
                                'An Unknown site codes result means the supplied value could not be '
                                'accepted against the current site inventory. It does not prove that '
                                'the physical site does not exist. Check spelling, identifier type, and '
                                'the latest inventory update. POP monitoring is not enabled merely by '
                                'accepting a similar-looking POP code.']),
                              ('Understanding the configured-site status',
                               ['The configured list gives a compact status per monitored site, while '
                                'the alarm drilldown explains all matched events. When several '
                                'categories affect a site, the compact status cannot describe every '
                                'event at once. Use the category badges and per-site View action for '
                                'the full picture.',
                                'A Site Down incident can make the site remain in Site Down after its '
                                'corresponding alarm is no longer present. This is deliberate: the card '
                                'combines relevant incident and alarm evidence. Inspect the '
                                'still-active incident before assuming the Mentor entry is stuck.',
                                'Removing a site changes only the monitoring selection. The original '
                                'inventory, incident history, and alarms still exist in their own '
                                'systems and can remain visible on other cards. If you later add the '
                                'site again, monitoring uses the current caches rather than restoring '
                                'an old snapshot of its alarms.'])],
                 'refresh_setting': 'APE_ALARM_SYNC_INTERVAL_SECONDS'},
 'card-ip-ezecom': {'title': 'IP Ezecom',
                    'group': 'Live alarm cards',
                    'intro': 'This card combines POP connectivity and power information with device '
                             'alarms. The groups do not all use the same query or counting method.',
                    'sections': [('Source and active rule',
                                  ['MSSQL noc.TBL_PPD supplies alarm rows. The EZE query reads alarm '
                                   'names beginning with EZE and keeps Status = 1 OR RestoredTime '
                                   'missing. Inventory joins use noc.TBL_ISPDEV and noc.TBL_POP. The '
                                   'local table is the Ezecom alarm cache.',
                                   'POP DOWN and POP POWER use the separate the cached POP alarm list '
                                   'query. It requires a non-null POP name and POP code after matching '
                                   'device IP to inventory. A missing mapping can remove a POP record '
                                   'before it reaches both its badge and drilldown.']),
                                 ('How counts work',
                                  ['POP DOWN/POWER count distinct POP name/code pairs. For EZE/TCT '
                                   'types, rows with both POP name and code are deduplicated by that '
                                   'pair. Rows without complete POP mapping count individually instead.',
                                   'Bandwidth and congestion types feed the Congestion badge. The '
                                   'current implementation adds separately counted types; this is not a '
                                   'distinct-interface total. A POP with both types can contribute '
                                   'through each type.']),
                                 ('Example: mapped sites versus rows',
                                  ['Three devices at the same mapped POP have one alarm type: they '
                                   'contribute 1 POP. Two more records without complete POP mapping '
                                   'contribute 2 individual records. The badge shows 3, while the '
                                   'drilldown can show five rows.']),
                                 ('What to inspect',
                                  ['Click the badge and compare alarm type, device, IP, interface, and '
                                   'timestamps. A saved congestion exclusion affects the selected '
                                   'interface on the identified device; it does not hide all ports.']),
                                 ('Why another system differs',
                                  ['Compare the same active rule, type, POP mapping, and sync time. Do '
                                   'not compare a mapped-site count with raw rows. Missing POP '
                                   'inventory is treated differently by the POP DOWN/POWER query and '
                                   'the general EZE/TCT type queries.']),
                                 ('Separate POP reachability from device alarms',
                                  ['A POP DOWN result describes the POP-oriented alarm query, while a '
                                   'port or congestion result can describe a device event. They may '
                                   'refer to the same location but they are not interchangeable '
                                   'conditions. A port can be congested without the POP being '
                                   'unreachable.',
                                   'For a missing POP record, check the relationship between device IP '
                                   'and POP inventory. A genuine alarm with an unmapped IP can fail the '
                                   'POP query requirement. The general Ezecom alarm query has different '
                                   'mapping rules, so the same device can still appear in another alarm '
                                   'group.',
                                   'Example: one POP has a router alarm and several port events. A '
                                   'POP-based badge can count the location once, while a device '
                                   'drilldown lists the router and ports separately. Use the interface '
                                   'field to decide which event you are inspecting rather than assuming '
                                   'every repeated POP name is a duplicate.']),
                                 ('Check congestion before excluding it',
                                  ['Read the device, IP, interface, and additional information '
                                   'together. Exclude only the port that has been intentionally '
                                   'accepted for exclusion and add a useful remark. A generic remark '
                                   'such as checked gives the next operator little context; describe '
                                   'why that interface should remain hidden.',
                                   'After exclusion, another port on the same router can still generate '
                                   'visible congestion. This is correct. If a source event later uses a '
                                   'different device identity or missing interface data, review its '
                                   'match rather than assuming every future alarm for that site should '
                                   'be hidden.'])],
                    'refresh_setting': 'MSSQL_SYNC_INTERVAL_SECONDS'},
 'card-ip-telcotech': {'title': 'IP Telcotech/Cellcard',
                       'group': 'Live alarm cards',
                       'intro': 'This card combines POP connectivity and power information with device '
                                'alarms. The groups do not all use the same query or counting method.',
                       'sections': [('Source and active rule',
                                     ['MSSQL noc.TBL_PPD supplies alarm rows. The TCT query reads alarm '
                                      'names beginning with TCT and keeps Status = 1 OR RestoredTime '
                                      'missing. Inventory joins use noc.TBL_ISPDEV and noc.TBL_POP. The '
                                      'local table is the Telcotech alarm cache.',
                                      'POP DOWN and POP POWER use the separate the cached POP alarm '
                                      'list query. It requires a non-null POP name and POP code after '
                                      'matching device IP to inventory. A missing mapping can remove a '
                                      'POP record before it reaches both its badge and drilldown.']),
                                    ('How counts work',
                                     ['POP DOWN/POWER count distinct POP name/code pairs. For EZE/TCT '
                                      'types, rows with both POP name and code are deduplicated by that '
                                      'pair. Rows without complete POP mapping count individually '
                                      'instead.',
                                      'Bandwidth and congestion types feed the Congestion badge. The '
                                      'current implementation adds separately counted types; this is '
                                      'not a distinct-interface total. A POP with both types can '
                                      'contribute through each type.']),
                                    ('Example: mapped sites versus rows',
                                     ['Three devices at the same mapped POP have one alarm type: they '
                                      'contribute 1 POP. Two more records without complete POP mapping '
                                      'contribute 2 individual records. The badge shows 3, while the '
                                      'drilldown can show five rows.']),
                                    ('What to inspect',
                                     ['Click the badge and compare alarm type, device, IP, interface, '
                                      'and timestamps. A saved congestion exclusion affects the '
                                      'selected interface on the identified device; it does not hide '
                                      'all ports.']),
                                    ('Why another system differs',
                                     ['Compare the same active rule, type, POP mapping, and sync time. '
                                      'Do not compare a mapped-site count with raw rows. Missing POP '
                                      'inventory is treated differently by the POP DOWN/POWER query and '
                                      'the general EZE/TCT type queries.']),
                                    ('Separate POP, device, and interface information',
                                     ['The POP badges summarize POP-oriented connectivity or power '
                                      'conditions. Other Telcotech/Cellcard groups come from device '
                                      'alarm types. One physical location can therefore contribute to '
                                      'several groups without representing several different POPs.',
                                      'A known IP address does not guarantee a complete POP mapping. If '
                                      'the inventory join cannot supply both required POP fields, a POP '
                                      'DOWN or POWER record can be absent from that query. Other type '
                                      'queries can still retain unmapped device records and count them '
                                      'individually.',
                                      'Example: a mapped POP has four device rows of one type, and a '
                                      'core device without POP mapping has two rows. The mapped group '
                                      'contributes one POP while the unmapped records contribute '
                                      'separately. Comparing that number to raw row totals without '
                                      'checking mapping gives a misleading mismatch.']),
                                    ('Read additional information before action',
                                     ['A bandwidth event can identify the specific interface in its '
                                      'Interface field and provide utilization details in Additional '
                                      'Information. Read those fields before excluding a record. The '
                                      'device name alone does not establish which port is congested.',
                                      'Excluding one interface is a local visibility decision. It is '
                                      'not an acknowledgment that all device problems were fixed, and '
                                      'it does not close an incident. Restore the exclusion when you '
                                      'want that qualifying port to appear again; unrelated interfaces '
                                      'and alarm types remain available.'])],
                       'refresh_setting': 'MSSQL_SYNC_INTERVAL_SECONDS'},
 'card-ran-site-down': {'title': 'RAN Status: Site Down',
                        'group': 'Live alarm cards',
                        'intro': 'Site Down identifies a complete outage by comparing the recognized '
                                 'alarm events with the technologies known to exist at the site.',
                        'sections': [('Source and classification',
                                      ['The service combines the cached Streamline alarm list, the '
                                       'cached site inventory, and the cached site technology '
                                       'inventory. Alarm events come from the Streamline alarm table; '
                                       'inventories establish which site is active and which '
                                       'generations must be checked.',
                                       'A recognized SRAN event represents shared-baseband loss. '
                                       'Otherwise, the union of down 2G/3G/4G/5G generations must cover '
                                       'the known technology inventory. Missing inventory prevents '
                                       'reliable classification by this comparison.']),
                                     ('Example: both technologies down',
                                      ['A site has 2G and 4G inventory. If only 4G is down, it is '
                                       'partially down and belongs in Tech Down. If both are down, it '
                                       'qualifies for Site Down even when neither source event says '
                                       'SRAN.']),
                                     ('SRAN is an event classification',
                                      ['NE is Disconnected, NE3SWS agent not responding to requests, '
                                       'and the link between the server and the ME is broken are SRAN '
                                       'events. eNodeB is out of service is 4G; Site Abis control link '
                                       'broken is 2G. Complete-site classification does not rewrite '
                                       'their source names to SRAN.']),
                                     ('Badges and detail rows',
                                      ['Hub-Site and grade badges narrow the site population. The same '
                                       'site can have multiple source events, so a site count is not '
                                       'necessarily a raw row count. Where an SRAN event exists, '
                                       'concurrent single-generation rows are suppressed in this '
                                       'complete-outage view. Without SRAN, the individual technology '
                                       'rows can remain visible.']),
                                     ('Verify an unexpected site',
                                      ['Check its actual alarm names, site code, On Air inventory '
                                       'match, and technology inventory. Compare all known generations, '
                                       'rather than assuming two alarm rows always mean the whole site '
                                       'is down.']),
                                     ('Follow the technology evidence in order',
                                      ['First identify the physical site and its known technologies. '
                                       'Then list which generations have qualifying down events. '
                                       'Finally compare the two sets. Counting repeated rows without '
                                       'this comparison can wrongly turn one failed generation into an '
                                       'apparent complete site outage.',
                                       'For example, inventory lists 2G and 4G. Two 4G events still '
                                       'cover only 4G. Adding a recognized 2G down event covers both '
                                       'generations and establishes the complete-outage condition. The '
                                       'evidence can remain as separate 2G and 4G rows because that is '
                                       'how the source reported it.',
                                       'A shared SRAN event follows the separate shared-baseband rule. '
                                       'Its presence can make the site completely down without needing '
                                       'individual events for every generation. This does not mean all '
                                       'future single-generation event names should be renamed SRAN.']),
                                     ('Grades explain the grouping, not the fault cause',
                                      ['A Hub-Site or grade badge tells you how the affected site is '
                                       'grouped in inventory. It does not describe the cause of its '
                                       'outage. Use the event information and incident investigation '
                                       'for that question.',
                                       'If the badge and source list differ, compare exact site codes, '
                                       'inventory coverage, event names, and latest update. An '
                                       'inventory change can alter complete-versus-partial '
                                       'classification even when an event row itself has not '
                                       'changed.'])],
                        'refresh_setting': 'APE_ALARM_SYNC_INTERVAL_SECONDS'},
 'card-ran-tech-down': {'title': 'RAN Status: Tech Down',
                        'group': 'Live alarm cards',
                        'intro': 'Tech Down means at least one recognized technology is down while the '
                                 'known inventory does not establish a complete site outage.',
                        'sections': [('How it is decided',
                                      ['The service compares down generations in the cached Streamline '
                                       'alarm list with the cached site technology inventory. It shares '
                                       'the complete-versus-partial classification with RAN Site Down. '
                                       'A recognized SRAN event is a shared-baseband condition, not an '
                                       'extra radio generation.']),
                                     ('Example: repeated 4G events',
                                      ['Inventory lists 2G, 3G, and 4G. A 4G outage alone is partial. '
                                       'Ten repeated 4G alarms do not prove all three generations '
                                       'failed. If qualifying events cover every inventoried '
                                       'generation, the site becomes a complete-outage case.']),
                                     ('Using the column',
                                      ['Click a Hub-Site or grade badge to inspect matching '
                                       'partial-outage records. The technology label follows the source '
                                       'event. If a site appears in an unexpected group, check missing '
                                       'inventory or an event name outside the supported classification '
                                       'list.']),
                                     ('Do not add overlapping counts blindly',
                                      ['One physical site can have several event rows. Compare site '
                                       'codes and technology coverage, not only the number of table '
                                       'rows or the sum of alarm types.']),
                                     ('Partial service loss can still be important',
                                      ['Tech Down is not a claim that the remaining technologies are '
                                       'healthy in every respect. It means the recognized down events '
                                       'do not cover the whole known site inventory. Users of the '
                                       'affected generation can still experience a serious service '
                                       'outage.',
                                       'A site with only 4G in inventory is different from a site with '
                                       'both 2G and 4G. A 4G down event can cover the entire first site '
                                       'but only part of the second. The same event text can therefore '
                                       'lead to different site-level classification depending on '
                                       'inventory.',
                                       'If another generation is physically present but absent from the '
                                       'saved inventory, the classification may not reflect the '
                                       'intended real-world site configuration. Check inventory quality '
                                       'before changing the interpretation of an alarm name.']),
                                     ('Worked comparison',
                                      ['Consider site A with 2G and 4G, and site B with 4G only. Both '
                                       'show eNodeB is out of service. Site A has a partial recognized '
                                       'outage; site B has all inventoried technology down. Comparing '
                                       'only the common event name misses this important distinction.',
                                       'When opening the detail table, read the site and technology '
                                       'together. An event-level row describes one observation. The '
                                       'site-level column summarizes the combined evidence, which is '
                                       'why event counts and site counts can differ.'])],
                        'refresh_setting': 'APE_ALARM_SYNC_INTERVAL_SECONDS'},
 'card-ran-power': {'title': 'RAN Status: Main AC and DC voltage',
                    'group': 'Live alarm cards',
                    'intro': 'These columns show power-related alarms. A power alarm does not by itself '
                             'prove that all site technologies are down.',
                    'sections': [('Main AC selection',
                                  ['Main AC Alarm reads the cached Streamline alarm list event names '
                                   'containing main failure, case-insensitively. A matching the cached '
                                   'site inventory entry supplies grade and Hub-Site metadata. Hub-Site '
                                   'takes precedence over the normal grade grouping.']),
                                 ('DC Low/High selection',
                                  ['DC Low/High selects event names containing high dc or low dc. It '
                                   'also requires the corresponding site inventory match. Complete '
                                   'outage classification is checked separately by the Site Down '
                                   'service.']),
                                 ('Example: power lost but site reachable',
                                  ['One site has Main AC Failure and Low DC Voltage together. It can '
                                   'contribute in each relevant power group while still operating on '
                                   'batteries. It need not appear in complete Site Down. These two '
                                   'alarms do not mean two different physical sites failed.']),
                                 ('Ticket references',
                                  ['Power-category incident information is preferred when enriching '
                                   'these alarms, with Site Down as a fallback. No matching ticket '
                                   'reference does not erase the underlying power alarm. Check the '
                                   'event, occurrence time, and associated incident before deciding '
                                   'that records conflict.']),
                                 ('Follow a power event through the site',
                                  ['When mains power fails, the site may continue operating from '
                                   'another supply. Later DC or generator-related events can describe '
                                   'the changing condition. Their presence at the same site does not '
                                   'establish several different sites, and their order matters when '
                                   'reconstructing what happened.',
                                   'For example, Main AC Failure begins at 09:00 and Low DC Voltage '
                                   'appears at 10:00. At 10:15 the site can still be reachable. These '
                                   'records establish power conditions, not a complete technology '
                                   'outage. Check the Site Down evidence separately before stating that '
                                   'service was entirely lost.',
                                   'Open the power badge, confirm the site code and occurrence time, '
                                   'and read the incident association. If the ticket category is Power, '
                                   'that is relevant context but not proof of a final root cause. A '
                                   'source event, an incident category, and Actual Root Cause are '
                                   'different pieces of information.',
                                   'Grade and Hub-Site values determine where a site is grouped. They '
                                   'do not change the meaning of High DC or Low DC. If a site is '
                                   'missing, verify its inventory match and supported event text before '
                                   'assuming the source alarm never existed.'])],
                    'refresh_setting': 'APE_ALARM_SYNC_INTERVAL_SECONDS'},
 'card-incident-status': {'title': 'Incident / INC-WO by Status',
                          'group': 'Incident cards',
                          'intro': 'An Incident is the main ticket. An INC-WO is a linked work order. '
                                   'The two sides of the card count different objects.',
                          'sections': [('Incident inclusion',
                                        ['the cached active incident list reads the Streamline incident '
                                         'table and keeps New or In Progress incidents. Customer '
                                         'Complaint is the exception: only In Progress is kept for that '
                                         'category. Other categories retain their normal active-status '
                                         'rules. Repeated site rows are not counted as extra incident '
                                         'IDs.']),
                                       ('Work-order inclusion',
                                        ['the cached active work-order list reads the Streamline '
                                         'work-order table joined to its the Streamline incident table '
                                         'parent. It excludes closed WOs and closed parents. Customer '
                                         'Complaint parents must be In Progress. WO badges then use WO '
                                         'statuses such as New, Assigned, Acknowledged, In Progress, '
                                         'Resolved, Reopened, Returned, and On Hold.']),
                                       ('Example: one ticket, three WOs',
                                        ['An In Progress incident has one Resolved WO and two In '
                                         'Progress WOs. It contributes one incident to the incident '
                                         'list, while the three WOs belong to their own status lists. A '
                                         'resolved WO does not mean its siblings are resolved or that '
                                         'the parent may be treated as closed.']),
                                       ('Overdue views',
                                        ['Overdue uses the source overdue result. Overdue L2 and L3 '
                                         'further narrow by support level. Overdue Site-Down narrows to '
                                         'the Site Down incident category. These are overlapping '
                                         'filtered views, not extra independent tickets to add to a '
                                         'grand total.']),
                                       ('Compare the same scope',
                                        ['Use the same incident category, parent status, and WO status '
                                         'in Streamline. All Records without those filters is a '
                                         'different population. Customer Complaint can remain in '
                                         'historical completion reporting even after leaving this '
                                         'active card.']),
                                       ('Read the parent and child records separately',
                                        ['When reviewing a ticket, first read the parent incident '
                                         'status. Then inspect its work orders. Several teams may be '
                                         'working on different WOs under one incident, so one team '
                                         'finishing does not mean the entire parent ticket is finished.',
                                         'For example, an incident has a field-service WO and a '
                                         'transmission WO. The field-service WO is Resolved, but the '
                                         'transmission WO remains In Progress. Both states are valid at '
                                         'once. The parent can remain In Progress while the individual '
                                         "WO badges describe each team's progress.",
                                         'An overdue badge is another view of the relevant records. A '
                                         'WO can be both In Progress and Overdue. Adding those two '
                                         'badge values would count that WO twice. Likewise, a Site Down '
                                         'overdue subset can overlap the general overdue population.',
                                         'For comparison with Streamline, decide whether you are '
                                         'filtering the incident table or the WO table. Apply the '
                                         'parent restrictions where needed and use the same statuses. A '
                                         'parent list of ten incidents can correctly correspond to more '
                                         'than ten work orders.'])],
                          'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-all-wo-resolved': {'title': 'All WO is Resolved: exact rules',
                          'group': 'Incident cards',
                          'intro': 'This badge counts qualifying incidents, not how many work orders '
                                   'they have. It verifies the source flag and the actual linked WO '
                                   'statuses.',
                          'sections': [('The exact checks',
                                        ['The parent incident must not be Closed and the All WO is '
                                         'Resolved flag must be TRUE. At least one linked the '
                                         'Streamline work-order table WO must exist, and every linked '
                                         'WO must have status resolved. A New, In Progress, Closed, '
                                         'reopened, or missing-status sibling blocks this strict '
                                         'result. Customer Complaint parents must also be In '
                                         'Progress.']),
                                       ('Why the extra WO check matters',
                                        ['The source flag can disagree with actual WO rows. Streamline '
                                         'filtering only All WO is Resolved = TRUE can therefore return '
                                         'more incidents than the dashboard. The extra verification '
                                         'prevents a stale flag from presenting unfinished WOs as fully '
                                         'resolved.']),
                                       ('Example: all five completed',
                                        ['Incident A has five WOs, all Resolved. The badge counts 1 '
                                         'incident. Its table row shows Total WOs = 5 and Resolved WOs '
                                         '= 5. The badge does not become 5, because its counting unit '
                                         'is an incident.']),
                                       ('Example: four of five completed',
                                        ['Incident B has four Resolved WOs and one In Progress WO. It '
                                         'is excluded even if its flag is TRUE. An incident with no '
                                         'linked WOs is also excluded; an empty set is not treated as a '
                                         'finished set.']),
                                       ('What the table columns mean',
                                        ['Total WOs counts all siblings before any status filter. '
                                         'Resolved WOs counts strictly Resolved siblings. Latest WO '
                                         'Resolved At is the latest sibling resolution timestamp, not '
                                         'proof the parent incident closed. Multi-site codes can share '
                                         'one incident row without multiplying the incident count.']),
                                       ('Refresh and drilldown',
                                        ['The incident job replaces the cached all-WO-resolved incident '
                                         'list with a complete source-verified snapshot. The drilldown '
                                         'uses that cache and periodically reloads its records. Browser '
                                         'reload alone does not re-run the source query; wait for a '
                                         'successful incident sync before comparing counts.']),
                                       ('A complete verification example',
                                        ['Incident A has two WOs, both Resolved, and the source All WO '
                                         'is Resolved flag is true. Its parent is not Closed, so it can '
                                         'qualify. Incident B has the same true flag but one WO is In '
                                         'Progress. The additional sibling check excludes B rather than '
                                         'trusting the flag alone.',
                                         'Incident C has every WO Resolved but the source flag is '
                                         'false. It does not qualify under the current rule because the '
                                         'badge requires both checks. This is important when '
                                         'reproducing the result: filtering only WO status is not '
                                         'equivalent to filtering only the incident flag, and neither '
                                         'alone reproduces both requirements.',
                                         'Incident D has a WO with status Closed rather than Resolved. '
                                         'The strict check does not treat those words as '
                                         'interchangeable. That distinction can explain an apparently '
                                         'finished incident missing from the badge. Inspect the exact '
                                         'source statuses instead of interpreting every '
                                         'finished-looking state as Resolved.',
                                         'When the parent later becomes Closed, it leaves this '
                                         'non-closed-incident badge. Its historical records are not '
                                         'deleted. If a total changes after an update, compare the '
                                         'incident IDs and sibling statuses before treating the '
                                         'decrease as lost data.'])],
                          'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-site-down-age': {'title': 'Site Down - Open (by Age)',
                        'group': 'Trend and performance cards',
                        'intro': 'This chart measures the age of currently active Site Down incidents. '
                                 'It is different from the duration of already completed outages.',
                        'sections': [('Source and count',
                                      ['The service reads the cached active incident list, narrows to '
                                       'Site Down, and counts each incident once rather than once for '
                                       'every site row. Age uses the occurrence timestamp and current '
                                       'Cambodia time.']),
                                     ('How this is calculated',
                                      ['Incident age = current Cambodia time minus Issue Occurred At. '
                                       'The chart counts distinct qualifying active Site Down incidents '
                                       'in each age range. Count the incident once even if it appears '
                                       'on several site-detail rows.',
                                       'Example: 13:00 minus 08:00 gives 5 hours. That incident belongs '
                                       'in 4-8h. If three incidents meet that range, the bar shows 3.']),
                                     ('Bucket boundaries',
                                      ['Buckets are below 4 hours, 4 to below 8, 8 to below 12, 12 to '
                                       'below 24, and 24 hours or more. The >24h label uses the last '
                                       'range including its 24-hour lower boundary. An incident can '
                                       'move to a later bucket without a new ticket being created.']),
                                     ('Example',
                                      ['An incident started at 08:00 Cambodia time. At 11:00 it belongs '
                                       'below 4 hours. At 13:00 it belongs in 4-8h. If it affects two '
                                       'sites, that does not automatically make it two incidents on '
                                       'this chart.']),
                                     ('Drilldown versus worklogs',
                                      ['A bar or count opens incidents in that age bucket. The worklog '
                                       'control uses separately cached source comments and audit '
                                       'changes. A chart count does not promise every incident has a '
                                       'worklog entry; availability of worklog data is a separate '
                                       'question.']),
                                     ('Verify differences',
                                      ['Check status, category, occurrence time, last sync, and whether '
                                       'the other screen counts tickets, sites, or alarm rows. Do not '
                                       'compare this current open-age cohort directly with the '
                                       'historical closed-outage duration cohort.']),
                                     ('Use age to prioritize an investigation',
                                      ['The age groups help identify incidents that have remained '
                                       'active longer. They do not directly measure SLA breach: two '
                                       'incident priorities can have different deadlines. A ticket in '
                                       'an older group deserves review, but use its actual SLA result '
                                       'rather than assuming the age label alone proves a missed '
                                       'target.',
                                       'An incident can move from 4-8h to 8-12h simply because time '
                                       'passed. No new source incident is required. If the incident '
                                       'resolves and stops matching the active query, it leaves the '
                                       'live chart after the source update. It can then be relevant to '
                                       'a historical completion report.',
                                       'For example, a ticket started at 06:00 and remains active at '
                                       '15:00. Its age is nine hours. If a worklog was added at 14:50, '
                                       'the ticket is still nine hours old; the recent comment does not '
                                       'reset the original incident occurrence time.',
                                       'When a worklog popup contains fewer incidents than the bar, '
                                       'check which tickets have actual cached worklog records. Do not '
                                       'interpret a missing worklog entry as proof the incident itself '
                                       'is absent from the age cohort.'])],
                        'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-volume': {'title': 'Incident Volume - Week over Week',
                 'group': 'Trend and performance cards',
                 'intro': 'This chart compares incident volumes over the selected reporting weeks. Its '
                          'source occurrence timestamp determines the incident cohort.',
                 'sections': [('Which date is used',
                               ['The incident-volume query reads the Streamline incident table and '
                                'returns Issue Occurred At as the trend date. Despite the internal '
                                'volume-cache name, this query is occurrence-based. It does not use the '
                                'active-only New/In Progress query.']),
                              ('How this is calculated',
                               ['Daily volume = the number of qualifying incident IDs whose occurrence '
                                'date belongs to that day, after applying the category and week '
                                'selections. Weekly volume = the sum of its daily incident counts.',
                                'Example: daily counts of 3, 4, 2, 5, 1, 0, and 2 produce a weekly '
                                'count of 17. These are incidents, not necessarily 17 different '
                                'sites.']),
                              ('Count and filters',
                               ['The service combines cached incident IDs with details and avoids '
                                'multiplying an incident by its site joins. Category and week '
                                'selections narrow the population. Default category exclusions can '
                                'differ from an explicitly selected category list.']),
                              ('Example: Sunday versus Monday',
                               ['A ticket occurred Sunday at 23:30 Cambodia time but was entered '
                                'Monday. An occurrence-based chart can place it in a different week '
                                'from a Streamline Created At filter. Match the date field before '
                                'comparing totals.']),
                              ('Clicking and exporting',
                               ['Click a day or value to inspect the corresponding records and '
                                'breakdowns. Use the same category and week selections in the export. '
                                'The current week is incomplete until it ends, so a lower current-week '
                                'total does not automatically mean a lower full-week volume.']),
                              ('Understand what a higher daily total means',
                               ['Volume describes how many qualifying incidents belong to the selected '
                                'period. It does not directly tell you how many are still open, how '
                                'many unique sites were affected, or how long the outages lasted. Use '
                                'status and duration views for those questions.',
                                'For example, Monday contains twenty qualifying incidents and Tuesday '
                                'contains ten. If many Monday tickets were quickly resolved, Monday can '
                                'still have the higher incident volume while Tuesday has more '
                                'unresolved work. These are not contradictory results.',
                                'A category filter changes which incidents contribute. Selecting Power '
                                'and Site Down includes the records in those selected categories; it '
                                'does not mean an incident was classified as both. Preserve the same '
                                'selection when comparing a day popup, drilldown, and exported records.',
                                'When a newly updated source record changes category or occurrence '
                                'time, its placement can change after the next successful sync. Compare '
                                'identifiers and date fields when explaining the change instead of '
                                'assuming the chart created or deleted tickets.'])],
                 'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-closed': {'title': 'Incidents Closed - Week over Week',
                 'group': 'Trend and performance cards',
                 'intro': 'This historical completion view is separate from the active incident card. '
                          'Its query includes specific Resolved records as well as Closed records.',
                 'sections': [('Source status rules',
                               ['The completed-incident query reads the Streamline incident table. '
                                'Customer Complaint uses status Resolved. Other categories accept '
                                'Closed or Resolved. The reporting date is Closed At if present, '
                                'otherwise Resolved At.']),
                              ('How this is calculated',
                               ['Completion date = Closed At when present, otherwise Resolved At. Daily '
                                'completion count = qualifying incident IDs assigned to that date. '
                                'Apply the category-specific accepted status rules before counting.',
                                'Example: four qualifying incidents have a completion date on Monday '
                                'and six on Tuesday. These two days contribute 10 completions. Their '
                                'original occurrence dates can be in earlier days or weeks.']),
                              ('Why an incident leaves one card but remains here',
                               ['An incident can leave the active New/In Progress population and remain '
                                'part of historical reporting. The Customer Complaint In Progress-only '
                                'rule for active cards does not remove completed complaints from this '
                                'historical trend.']),
                              ('Example',
                               ['A Power incident has no Closed At but was resolved Tuesday. It can be '
                                'included under that resolution date. If Closed At is later populated, '
                                'the preferred completion timestamp can change its historical placement '
                                'after sync.']),
                              ('How to verify',
                               ['Match the included statuses and Closed At, falling back to Resolved At '
                                'date. Streamline Status = Closed alone cannot reproduce a query that '
                                'also accepts Resolved. Then apply the same categories and weeks.']),
                              ('Completion is different from outage start',
                               ["A completion trend answers when work reached the query's accepted "
                                'completed statuses. An occurrence trend answers when incidents began. '
                                'An incident spanning several days can therefore contribute to '
                                'different dates on these two charts.',
                                'For example, an outage begins Friday and its incident completes '
                                'Monday. The completion view can show it on Monday even though the '
                                "operational problem began in the previous week. Comparing Friday's "
                                "volume directly with Monday's completion count does not compare the "
                                'same cohort.',
                                'If both resolution and closing times exist, the preferred date rule '
                                'determines the completion date. Review those fields in the source when '
                                'a record moves between reporting weeks. Do not assume the time a user '
                                'noticed the status change is the source completion timestamp.',
                                'This is historical reporting, so a ticket leaving the active card is '
                                'expected to remain available here when it meets the completion rules. '
                                'Retaining that history is different from retaining an outdated active '
                                'alarm.'])],
                 'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-duration': {'title': 'Site-Down Duration - Weekly Trend',
                   'group': 'Trend and performance cards',
                   'intro': 'This chart groups completed Site Down incidents by outage duration. It '
                            'does not measure how long the currently open tickets have existed.',
                   'sections': [('Source conditions',
                                 ['The historical Site Down query keeps Site Down incidents with status '
                                  'Closed, a recorded Resolved At, and Closed At inside the reporting '
                                  'window. Outage duration uses occurrence to resolution; closing time '
                                  'scopes the historical window.']),
                                ('How this is calculated',
                                 ['Outage duration = Resolved At minus Issue Occurred At. For '
                                  'qualifying closed Site Down incidents, assign that duration to '
                                  'exactly one duration bucket and count the matching incidents for the '
                                  'selected closing week.',
                                  'Example: 10:30 minus 08:00 is 2 hours 30 minutes, so the record '
                                  'belongs in the group above 15 minutes and below 4 hours. The first '
                                  'bucket includes exactly 15 minutes; 4 hours enters 4-8h and exactly '
                                  '24 hours enters the final bucket.']),
                                ('Duration groups',
                                 ['The labels are up to 15 minutes, 16m-4h, 4-8h, 8-12h, 12-24h, and '
                                  'above 24h. Inspect exact timestamps in the drilldown for a record '
                                  'close to a boundary. Week and duration choices can also narrow '
                                  'related root-cause views.']),
                                ('Example',
                                 ['An incident occurred 08:00, was resolved 10:30, and closed 12:00. '
                                  'Its outage duration is 2 hours 30 minutes, not 4 hours. It belongs '
                                  'in 16m-4h. An incident still open does not qualify for this '
                                  'closed-incident dataset.']),
                                ('Comparing lines',
                                 ['Selected weeks determine the compared cohorts. A partial '
                                  'current-week line contains only data available so far. Count '
                                  'incident IDs rather than individual alarm occurrences when checking '
                                  'totals.']),
                                ('Duration is not closing delay',
                                 ['A site can be restored before administrative closing is completed. '
                                  'The difference between resolution and closing does not automatically '
                                  'extend the measured outage duration in this chart. Read the selected '
                                  "duration formula before comparing it with a ticket's total lifetime.",
                                  'For example, service returns at 10:00 but the ticket is closed at '
                                  '16:00 after verification. If the outage began at 08:00, the measured '
                                  'occurrence-to-resolution interval is two hours. The later closing '
                                  'time can affect historical eligibility without making the outage '
                                  'eight hours long.',
                                  'Two incidents of the same duration can belong to different reporting '
                                  'weeks because their closing dates differ. A duration bucket is not '
                                  'an identifier or an independent event; it is a grouping of '
                                  'qualifying historical incident records.',
                                  'If an apparent duration is negative or a required timestamp is '
                                  'missing, inspect the original times rather than treating it as a '
                                  'genuine fast restoration. Source timestamp quality is part of a '
                                  'reliable duration comparison.'])],
                   'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-top-sites': {'title': 'Top 10 Site Down - Overtime',
                    'group': 'Trend and performance cards',
                    'intro': 'This ranking highlights sites with frequent qualifying historical Site '
                             'Down incidents. It does not mean every ranked site is currently down.',
                    'sections': [('Source and ranking',
                                  ['The service uses the historical Site Down duration dataset with '
                                   'site details. It ranks site codes by incident participation in the '
                                   'selected weeks. Frequency is a different measure from the longest '
                                   'single outage duration.']),
                                 ('How this is calculated',
                                  ['Site frequency = the number of qualifying incident associations for '
                                   'each site within the selected historical cohort. Sort sites by that '
                                   'count and show the highest-ranked ten.',
                                   'Example: site A appears in 5 incidents, B in 3, and C in 2. The '
                                   'order is A, B, C by frequency. This formula does not rank the '
                                   'longest outage or calculate unique affected sites across all '
                                   'incidents.']),
                                 ('Example',
                                  ['Site 0460 has five qualifying incidents and 1002 has two. Frequency '
                                   'can place 0460 higher even when 1002 had the longest individual '
                                   'outage. One multi-site incident may relate to more than one ranked '
                                   'site.']),
                                 ('Linked root-cause view',
                                  ['Click a site code to filter the adjacent Root Cause Breakdown to '
                                   'that site. Without a selected site, that breakdown uses the '
                                   'top-ranked sites together. The selected Top 10 weeks also affect '
                                   'the related breakdown.']),
                                 ('No data',
                                  ['An empty chart means there are no qualifying records in the current '
                                   'cached window and filters. It is not proof there are no outages '
                                   'anywhere. On startup, allow the relevant sync to complete before '
                                   'interpreting an initially empty card.']),
                                 ('Read the ranking without confusing frequency and impact',
                                  ['A high position means frequent qualifying incident participation in '
                                   'the selected cohort. It does not establish the largest customer '
                                   'impact, the longest total downtime, or the highest priority. Those '
                                   'require their own measures and source details.',
                                   'For example, site A has six short incidents and site B has one long '
                                   'outage. A frequency ranking can place A first, while a '
                                   'duration-based investigation might prioritize B. State which '
                                   'measure you mean when explaining the top site to another user.',
                                   'Changing the selected weeks changes the ranking population and can '
                                   'change which sites enter the top ten. A root-cause view linked to '
                                   'those ranked sites can therefore change even when no cause label '
                                   'was edited. Its inputs changed with the ranking.',
                                   'When reviewing a selected site, inspect the incident IDs and '
                                   'affected site codes. Several sites can be linked to one parent '
                                   'incident, so adding site-specific incident counts may not reproduce '
                                   'the number of unique incidents across the network.'])],
                    'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-root-causes': {'title': 'Site-Down Root Cause and Root Cause Breakdown',
                      'group': 'Trend and performance cards',
                      'intro': 'These views group historical records by recorded Root Cause Category. '
                               'They follow different filters, so the same category can have different '
                               'totals in each view.',
                      'sections': [('Root Cause Breakdown',
                                    ['This view follows Top 10 Site Down: the ranked sites together, or '
                                     'one selected site, with its selected weeks. It is not a summary '
                                     'of every site in the source database.']),
                                   ('How this is calculated',
                                    ['Category share = the category count divided by the total counted '
                                     'entries in that filtered breakdown, multiplied by 100. The '
                                     'population includes its applicable missing-cause group; multiple '
                                     'recorded categories can contribute separately.',
                                     'Example: 4 Power entries out of 10 total entries give 40%. '
                                     'Selecting a site or duration bucket changes the denominator. '
                                     'Percentages can have rounding differences and are not percentages '
                                     'of all network alarms.']),
                                   ('Site-Down Root Cause - Breakdown',
                                    ['This view follows the Site-Down Duration week and duration '
                                     'selections. Narrowing to a duration bucket changes its incident '
                                     'population. Check subtitles and filters before comparing it with '
                                     'the Top 10-linked view.']),
                                   ('Missing and multiple causes',
                                    ['The root-cause lookup uses recorded Root Cause Categories. '
                                     'Missing causes remain an unassigned group rather than being '
                                     'guessed from notes. A rare incident carrying several recorded '
                                     'categories can contribute to each applicable category; do not '
                                     'assume the sum of category counts always equals unique incident '
                                     'IDs.']),
                                   ('Example and percentages',
                                    ['A selected site has six qualifying incidents: four with recorded '
                                     'causes and two without. The unassigned group explains the missing '
                                     'classifications. Changing the selected site or duration group '
                                     'changes the percentage base even if category names remain the '
                                     'same.']),
                                   ('Open the records',
                                    ['Click a category to inspect matching incidents. The chart and '
                                     'table provide different presentations of the same selected '
                                     'context. Percentages refer to that filtered breakdown, not all '
                                     'active alarms globally.']),
                                   ('Keep the selected population visible in your explanation',
                                    ['Before reading a cause percentage, identify what the chart is '
                                     'summarizing: one selected site, the top-ranked sites, or a '
                                     'duration-filtered incident population. A percentage without that '
                                     'context is easy to misunderstand.',
                                     'For example, Power is four of eight classifications in one '
                                     'filtered population and four of twenty in another. The label and '
                                     'count are unchanged, but the percentage differs because the '
                                     'denominator changed. This does not mean the system edited the '
                                     'cause.',
                                     'An unassigned cause means the relevant category is not recorded '
                                     'in the matched data. It should not be silently converted into the '
                                     'incident note, a suspected fault, or an alarm event name. Those '
                                     'fields may contain useful investigation context but they do not '
                                     'substitute for the recorded Root Cause Category.',
                                     'When a cause is assigned later, the next qualifying update can '
                                     'move the incident from unassigned to that category. Historical '
                                     'breakdowns can therefore become more complete after operational '
                                     'work finishes. Inspect the source category and cohort when '
                                     'explaining a changed slice.'])],
                      'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-sla': {'title': 'SLA Compliance - Weekly Trends',
              'group': 'Trend and performance cards',
              'intro': 'Each incident has two separate deadline results: Response SLA and Resolution '
                       'SLA. Passing one does not guarantee passing the other.',
              'sections': [('Source fields',
                            ['the Streamline incident table supplies the Response SLA overdue field for '
                             'Response and the Resolution SLA overdue field for Resolution. FALSE means '
                             'Met; TRUE means Not Met. A missing Resolution result is Not Graded, not '
                             'automatically a pass or a failure. Detail targets come from saved SLA '
                             'policy rules matching category, support level, and applicable priority or '
                             'site grade.']),
                           ('How this is calculated',
                            ['Response Compliance = Response Met count divided by the response cohort '
                             'count, multiplied by 100. Resolution Compliance = Resolution Met count '
                             'divided by the graded resolution cohort count, multiplied by 100. A '
                             'missing Resolution result is excluded from the graded denominator.',
                             'Example: Response Met 90 out of 100 gives 90%. Resolution Met 30 out of '
                             '40 graded gives 75%. Combine selected categories by adding their counts '
                             'first; do not take an unweighted average of category percentages.',
                             'For the root-cause table, Response Not Met = count of matching incidents '
                             'with a failed Response result. Resolution Not Met = count with a failed '
                             'Resolution result. An incident failing both contributes once in each '
                             'column. The root-cause occurrence-week cohort is separate from the '
                             'summary response-created and resolution-closed week cohorts.']),
                           ('Weekly percentages',
                            ['Response Compliance is Response Met divided by its response cohort. '
                             'Resolution Compliance uses graded Resolution records, excluding ungraded '
                             'values from that denominator. The summary groups Response by Created At '
                             'week and Resolution by Closed At week in Cambodia time. These are '
                             'different cohorts.']),
                           ('Example: the rate',
                            ['If 90 of 100 response records are Met, Response Compliance is 90%. If 30 '
                             'of 40 graded resolution records are Met, Resolution Compliance is 75%. '
                             'Ten additional ungraded resolution records must not silently become ten '
                             'successful resolutions.']),
                           ('Root Cause table',
                            ['The columns are Root Cause Category, Response Not Met, and Resolution Not '
                             'Met. It uses incidents that missed either result in the occurrence-week '
                             'cohort, with selected categories applied. This week anchor differs from '
                             'the summary pass-rate Created At and Closed At anchors. A failed incident '
                             'without a root-cause category stays under Not Assigned.']),
                           ('Example: why 15 and 19 are different lists',
                            ['Suppose 13 incidents missed only Response, 2 missed both, and 17 missed '
                             'only Resolution. Response Not Met shows 15. Resolution Not Met shows 19. '
                             'Clicking 15 opens the response list; only 2 of those also show Resolution '
                             'Not Met. Clicking 19 opens the separate resolution list. These are '
                             'illustrative figures, not current live data.']),
                           ('How to verify a number',
                            ['Click the specific failure count for the selected cause. Its drilldown '
                             'and export apply the corresponding Response or Resolution flag, cause '
                             'label, selected categories, and occurrence week. In Streamline, match '
                             'that exact overdue field and date field, not just the week number.']),
                           ('Response and resolution measure different parts of the work',
                            ['Response concerns how quickly the incident was taken up against its '
                             'response requirement. Resolution concerns completing the incident against '
                             'its resolution requirement. An early response can still be followed by a '
                             'long repair, and a late response can still be followed by a repair that '
                             'meets its separate target.',
                             'This is why the two Not Met columns are not steps in one calculation. '
                             'Resolution Not Met is not supposed to equal the number of Resolution '
                             'failures visible inside the Response Not Met list. Each column starts '
                             'from its own failure condition within the selected root-cause cohort.',
                             'Imagine two lists of names. The Response list contains fifteen names; the '
                             'Resolution list contains nineteen. Two names happen to be on both lists. '
                             'Opening the first list reveals those two shared incidents, but it does '
                             'not reveal the seventeen additional resolution-only incidents. Open the '
                             'Resolution count to see those records.',
                             'A Not Graded resolution is a third outcome, not the same as Met. When '
                             'checking an incident that appears absent from a failed-resolution list, '
                             'read the recorded result before assuming the system considers it '
                             'successful.'])],
              'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-response-time': {'title': 'Response Time - Week over Week',
                        'group': 'Trend and performance cards',
                        'intro': 'This card measures elapsed response time, not the percentage of '
                                 'incidents meeting an SLA target.',
                        'sections': [('Timestamp calculation',
                                      ['The source is the Streamline incident table. The interval ends '
                                       'at Taken In Progress At. When the ticket was created manually, '
                                       'it starts at Created At; otherwise it starts at Issue Occurred '
                                       'At. This avoids counting a backdated occurrence as elapsed time '
                                       'before the manual ticket existed.',
                                       "The query groups by the chosen start timestamp's Cambodia week. "
                                       "Do not assume this timing chart shares the SLA summary's "
                                       'Created At or Closed At anchor.']),
                                     ('How this is calculated',
                                      ['Response duration = Taken In Progress At minus the applicable '
                                       'start time. Start time is Created At for a manually created '
                                       'incident, otherwise Issue Occurred At. Average = total '
                                       'qualifying response minutes divided by the number of measured '
                                       'incidents. Minimum and maximum are the shortest and longest '
                                       'measured values.',
                                       'Example: measured responses of 10, 20, and 60 minutes give an '
                                       'average of 30 minutes, minimum 10, and maximum 60. When '
                                       'combining categories, weight each category average by its '
                                       'measured incident count.',
                                       'The displayed comparison uses the absolute change from the '
                                       'previous value divided by the previous value, multiplied by '
                                       '100. The display rounds and caps it at 100%; a smaller duration '
                                       'is an improvement. A zero or missing previous value has no '
                                       'percentage comparison.']),
                                     ('Average, minimum, and maximum',
                                      ['Average is an arithmetic mean, not a median. A few slow '
                                       'incidents can raise it substantially. Minimum and maximum '
                                       'describe the extremes of the qualifying measured records. '
                                       'Missing required timestamps do not establish a zero-minute '
                                       'response or resolution.']),
                                     ('Example',
                                      ['A manual ticket was created 09:00 even though its occurrence '
                                       'was entered as 07:00. If its response endpoint is 10:00, the '
                                       'manual measured interval is 1 hour. An automatically created '
                                       'incident with 07:00 occurrence and 10:00 endpoint uses 3 '
                                       'hours.']),
                                     ('What the result does not prove',
                                      ['A high average does not prove every incident breached SLA. '
                                       'Targets can differ by priority and support level. Inspect the '
                                       'individual timestamps and selected categories; compare a '
                                       'partial current week cautiously with completed weeks.']),
                                     ('Use elapsed time alongside the SLA result',
                                      ['A measured response duration tells you how long a qualifying '
                                       'incident took to reach its response endpoint. It does not by '
                                       'itself say whether the response was acceptable: that depends on '
                                       'the applicable SLA target.',
                                       'For example, two incidents can both take thirty minutes to '
                                       'respond to. If their applicable deadlines differ, one may meet '
                                       'its requirement while the other does not. The timing chart and '
                                       'compliance card answer related but different questions.',
                                       'An average is sensitive to unusually slow cases. If most '
                                       'responses are short but one incident waited many hours, the '
                                       'mean rises. Use the maximum and individual detail records to '
                                       'understand that pattern rather than concluding that every team '
                                       'response was slow.',
                                       'When an endpoint is missing, there is no measured completed '
                                       'response interval for that row. Do not substitute the current '
                                       'time or zero unless that particular view explicitly defines '
                                       'such a rule. Check the source fields and reporting cohort.'])],
                        'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-resolution-time': {'title': 'Resolution Time - Week over Week',
                          'group': 'Trend and performance cards',
                          'intro': 'This card measures elapsed resolution time, not the percentage of '
                                   'incidents meeting an SLA target.',
                          'sections': [('Timestamp calculation',
                                        ['The source is the Streamline incident table. The interval '
                                         'ends at Resolved At. When the ticket was created manually, it '
                                         'starts at Created At; otherwise it starts at Issue Occurred '
                                         'At. This avoids counting a backdated occurrence as elapsed '
                                         'time before the manual ticket existed.',
                                         "The query groups by the chosen start timestamp's Cambodia "
                                         'week. Do not assume this timing chart shares the SLA '
                                         "summary's Created At or Closed At anchor."]),
                                       ('How this is calculated',
                                        ['Resolution duration = Resolved At minus the applicable start '
                                         'time. Start time is Created At for a manually created '
                                         'incident, otherwise Issue Occurred At. Average = total '
                                         'qualifying resolution minutes divided by the number of '
                                         'measured incidents; minimum and maximum are the extremes.',
                                         'Example: measured durations of 60, 120, and 180 minutes give '
                                         'a 120-minute average. If another category has more incidents, '
                                         'combine the underlying counts and duration totals, not a '
                                         'simple average of category averages.',
                                         'The displayed comparison uses the absolute change divided by '
                                         'the previous value, multiplied by 100, rounded and capped at '
                                         '100%. A smaller duration is better. No percentage change is '
                                         'calculated from a zero or missing previous value.']),
                                       ('Average, minimum, and maximum',
                                        ['Average is an arithmetic mean, not a median. A few slow '
                                         'incidents can raise it substantially. Minimum and maximum '
                                         'describe the extremes of the qualifying measured records. '
                                         'Missing required timestamps do not establish a zero-minute '
                                         'response or resolution.']),
                                       ('Example',
                                        ['A manual ticket was created 09:00 even though its occurrence '
                                         'was entered as 07:00. If its resolution endpoint is 10:00, '
                                         'the manual measured interval is 1 hour. An automatically '
                                         'created incident with 07:00 occurrence and 10:00 endpoint '
                                         'uses 3 hours.']),
                                       ('What the result does not prove',
                                        ['A high average does not prove every incident breached SLA. '
                                         'Targets can differ by priority and support level. Inspect the '
                                         'individual timestamps and selected categories; compare a '
                                         'partial current week cautiously with completed weeks.']),
                                       ('Separate repair time, closing time, and compliance',
                                        ['Resolution time measures the configured start-to-resolution '
                                         'interval. Closing can happen later for verification or '
                                         'administrative reasons. A closing timestamp and a resolution '
                                         'timestamp should not be used interchangeably when validating '
                                         'this chart.',
                                         'For example, work begins in the morning, the incident '
                                         'resolves in the afternoon, and closing is completed the next '
                                         'day. The elapsed resolution measure ends at resolution. A '
                                         'completion report anchored to closing can still place that '
                                         'same ticket in a different daily or weekly cohort.',
                                         'A long duration does not automatically prove an SLA breach '
                                         'without considering the applicable target. Likewise, a low '
                                         'overall average can coexist with several serious breaches. '
                                         'Review the specific incident result and target when making a '
                                         'compliance statement.',
                                         'When investigating an extreme value, compare the creation '
                                         'method and start timestamp first. A manually backdated '
                                         'occurrence should not be mistaken for time before the ticket '
                                         'existed when the calculation uses the manual Created At '
                                         'rule.'])],
                          'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'},
 'card-congestion': {'title': 'Congestion and interface exclusions',
                     'group': 'Monitoring and data',
                     'intro': 'A congestion exclusion is a saved interface-specific visibility rule. It '
                              'does not resolve or delete the source alarm.',
                     'sections': [('Active alarms versus history',
                                   ['Current EZE/TCT alarms and historical congestion charts use '
                                    'separate queries in the IP alarm source queries. Active queries '
                                    'use their current active-record condition. Historical congestion '
                                    'uses its reporting cutoff and can include records that later '
                                    'cleared. Do not expect the historical chart to be the same list as '
                                    'current open alarms.']),
                                  ('Exact exclusion scope',
                                   ['Review device and interface before excluding. The key includes '
                                    'owner, device identity, and interface. It uses IP where available, '
                                    'otherwise device name. It does not hide the entire device or every '
                                    'site sharing a site code.']),
                                  ('Example: only one port',
                                   ['Device A has congestion on XGigabitEthernet0/0/22 and '
                                    'XGigabitEthernet0/0/23. Excluding port 22 hides its congestion on '
                                    "Device A. Port 23 stays visible. Device B's port 22 is not "
                                    'automatically hidden. Other alarm types are unaffected.']),
                                  ('Remarks, blacklist, and restore',
                                   ['Add a remark explaining the exclusion. Blacklist shows interface, '
                                    'additional information, note, remark, and other saved metadata '
                                    'when available. Restore removes the visibility rule. It cannot '
                                    'recreate an alarm that no longer qualifies in the source.']),
                                  ('Persistence',
                                   ['Rules live in the instance SQLite data and survive refresh and '
                                    'restart. Normal source sync does not erase them. Keep the entire '
                                    'instance folder when upgrading. Legacy rules lacking an interface '
                                    'are not treated as broad device exclusions.']),
                                  ('A remark should explain the operational reason',
                                   ['Before saving an exclusion, confirm that its interface matches the '
                                    'record you intended. Similar device names and reused port labels '
                                    'make it important to read the IP and owner too. A port exclusion '
                                    'on one device is not a rule for every similarly named port.',
                                    'Write a remark that another operator can understand later, such as '
                                    'an approved monitoring exception and its reason. The remark '
                                    'documents your decision; it is not a new alarm measurement or '
                                    'proof that utilization returned to normal.',
                                    'If the device develops a second congested interface, that other '
                                    'port should remain visible. Seeing it after excluding the first '
                                    'port is correct behavior. Do not repeatedly exclude every '
                                    'remaining row unless each interface has its own valid operational '
                                    'reason.',
                                    'Restore means remove the local visibility exception. A qualifying '
                                    'active alarm can then reappear, while an already-cleared source '
                                    'record may remain absent from the current list. Historical views '
                                    'and current-alarm views can still show different populations.'])],
                     'refresh_setting': 'CONGESTION_SYNC_INTERVAL_SECONDS'},
 'card-refresh': {'title': 'Cache, refresh, Cambodia time, and verification',
                  'group': 'Monitoring and data',
                  'intro': 'The dashboard reads local cached records so opening a card does not '
                           'repeatedly query every source system.',
                  'sections': [('From source query to card',
                                ['A background job runs PostgreSQL or MSSQL SQL, normalizes fields and '
                                 'timestamps, and writes a local snapshot under instance. Services read '
                                 'the snapshot, apply counting rules, and render cards and drilldowns. '
                                 'Browser refresh reloads that cached view; it does not guarantee a new '
                                 'source query.']),
                               ('Not every job uses five minutes',
                                ['Incident and WO sync defaults to 300 seconds. APE, VIP, and many '
                                 'inventory jobs also default to 300 seconds. Active MSSQL alarms '
                                 'default to 10 seconds; historical congestion defaults to 300 seconds. '
                                 'Environment settings can override these values. Source availability '
                                 'and query completion affect when new data actually appears.']),
                               ('Cache dependencies',
                                ['VIP alarms depend on both alarm and inventory caches. An incident may '
                                 'arrive before its matching inventory or alarm update. Jobs do not all '
                                 'commit at the same instant. A failed source fetch can leave the last '
                                 'successful snapshot visible.']),
                               ('Cambodia date rules',
                                ['The application uses Asia/Phnom_Penh, UTC+7. Convert source UTC '
                                 'timestamps once. Occurred At, Created At, Resolved At, and Closed At '
                                 'are different fields. A Sunday-night occurrence closed Monday morning '
                                 'can belong to different weeks in occurrence and completion reports.']),
                               ('Updates and saved data',
                                ['Keep instance for saved exclusions, Mentor sites, reports, and alert '
                                 'history, and keep .env for connections and delivery settings. Live '
                                 'caches continue refreshing after startup. Retaining instance does not '
                                 'freeze source data. Run only one dashboard version to avoid '
                                 'overlapping jobs and delivery.']),
                               ('Comparison checklist',
                                ['Match category, statuses, date field, timezone, week, and counting '
                                 'unit. Compare IDs as well as totals. Confirm whether a badge counts '
                                 'sites while its drilldown lists alarm rows. Then check the last '
                                 'successful sync before concluding a record is missing.']),
                               ('What five minutes means during a real update',
                                ['A five-minute job interval is a schedule, not a countdown '
                                 'guaranteeing that every screen changes exactly five minutes after a '
                                 'source edit. The job must start, reach the source successfully, '
                                 'finish its query, save the result, and then the browser must load the '
                                 'relevant view.',
                                 'For example, a ticket changes just after its job collected data. It '
                                 'can remain in the previous state until the next successful cycle. If '
                                 'the source query fails, the last successful snapshot can remain '
                                 'visible longer. Repeated browser refreshes do not make that source '
                                 'request succeed.',
                                 'Preserving instance during an upgrade keeps saved settings and '
                                 'history, but it also initially carries the last cached snapshots. '
                                 'After startup the normal jobs replace the source-backed caches. This '
                                 'is expected and does not mean the upgrade froze the old records '
                                 'permanently.',
                                 'When explaining a stale value, distinguish three times: the source '
                                 'record timestamp, the successful cache-update time, and the time the '
                                 'browser displayed the page. They describe different steps. A clean '
                                 'comparison checks the identifiers and relevant timestamps at each '
                                 'step.'])],
                  'refresh_setting': 'INCIDENT_SYNC_INTERVAL_SECONDS'}}
