# 📊 Comprehensive Evaluation & Hunk Alignment Report

This detailed analytics dashboard consolidates success counts, hunk complexities, patch alignments, and fallback impact metrics across all evaluation runs.

---

## 📈 Executive Summary Dashboard

| Metric | Baseline (Without Fallback) | Final System (With Fallback) | Net Impact |
| :--- | :---: | :---: | :---: |
| **Pipeline Runs Count** | `490` | `490` | — |
| **Successful Backports** | `390` | `424` | **+34 Succeeded** |
| **Backport Success Rate** | `79.59%` | `86.53%` 🟢 | **+6.94%** |

### System Success Progress
```text
[#####################----] 86.5%
```

---

## 🛡️ Fallback Agent Performance Impact

The fallback agent handles complex failures, context mismatch errors, and compile regressions to recover patches.

| Fallback Outcome Category | Count | Percentage | Description |
| :--- | :---: | :---: | :--- |
| **Succeeded BEFORE Fallback** | `390` | `79.6%` | Succeeded on standard run without fallback intervention. |
| **Succeeded AFTER Fallback (Improved)** | `34` | `6.9%` | Saved by Fallback Agent after standard runs failed. |
| **Failed Both (Baseline & Fallback)** | `66` | `13.5%` | Unresolved failures despite fallback engagement. |
| **Regressed (Broke Working Patches)** | `0` | `0.0%` | Working patches broken after fallback run. |

### 🏷️ Fallback Type-Wise Performance Breakdown

| Patch Type | Total Patches | Baseline Rate (No Fallback) | Final Success Rate | Improved Count | Net Lift |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `TYPE-I` | **232** | `92.2%` | `95.3%` | `+7` | `+3.0%` |
| `TYPE-II` | **150** | `88.7%` | `92.0%` | `+5` | `+3.3%` |
| `TYPE-III` | **23** | `52.2%` | `69.6%` | `+4` | `+17.4%` |
| `TYPE-IV` | **5** | `80.0%` | `80.0%` | `+0` | `+0.0%` |
| `TYPE-V` | **79** | `34.2%` | `57.0%` | `+18` | `+22.8%` |
| `unknown` | **1** | `0.0%` | `0.0%` | `+0` | `+0.0%` |

---

## 📦 Hunk Distribution & Complexity Analysis

Complexity is analyzed focusing on **Java Production Hunks** while filtering out test scripts and non-Java metadata files.

* **Total Java Production Hunks Evaluated**: `2653`
* **Total Developer Auxiliary/Test Hunks**: `1135`
* **Total Failed Hunks Recorded**: `91`
* **Average Java Production Hunks per Patch**: `5.41` hunks
* **Average Auxiliary Hunks per Patch**: `2.32` hunks

### 🏷️ Hunk Composition by Patch Type

| Patch Type | Count | Total Java Prod | Total Aux/Test | Avg Java Prod | Avg Aux | Failed Hunks |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `TYPE-I` | **232** | `1129` | `496` | `4.87` | `2.14` | `3` |
| `TYPE-II` | **150** | `675` | `379` | `4.50` | `2.53` | `10` |
| `TYPE-III` | **23** | `141` | `50` | `6.13` | `2.17` | `11` |
| `TYPE-IV` | **5** | `46` | `7` | `9.20` | `1.40` | `3` |
| `TYPE-V` | **79** | `662` | `203` | `8.38` | `2.57` | `64` |
| `unknown` | **1** | `0` | `0` | `0.00` | `0.00` | `0` |

---

## ⚖️ Patch hunk Alignment Comparison (Developer vs. Agent)

This section maps the structural similarity between the Developer's baseline patch (`target.patch`) and the Agent's generated patch (`generated.patch`).

### 📐 Hunk Alignments Metrics

| Statistic | Developer (Target) | Agent (Generated) | Developer Aux |
| :--- | :---: | :---: | :---: |
| **Sum Total** | `3133` | `3197` | `1135` |
| **Mean Hunks / Patch** | `6.39` | `6.52` | `2.32` |
| **Median Hunks / Patch** | `4.0` | `4.0` | `2.0` |
| **Min / Max hunks** | `1 / 56` | `0 / 58` | `0 / 22` |

### 📐 Match Alignment Differences (Generated - Developer)

| Comparison Outcome | Run Count | Percentage | Interpretation |
| :--- | :---: | :---: | :--- |
| **Perfect Match (Same Hunks)** | `201` | `41.0%` | Agent matches developer structural complexity exactly. |
| **Fewer Hunks in Generated** | `155` | `31.6%` | Agent consolidated modifications or simplified hunks. |
| **More Hunks in Generated** | `134` | `27.3%` | Agent introduced extra context hunks or verbose code. |

**Mean Hunk Count Shift**: `0.13`

---

## 📁 Repository Patch Alignments Table

| Repository | Patches | Dev Hunks | Gen Hunks | Matches | Match Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `crate` | **127** | `730` | `808` | `60` | `47.2%` |
| `druid` | **7** | `96` | `90` | `3` | `42.9%` |
| `elasticsearch` | **93** | `470` | `313` | `53` | `57.0%` |
| `graylog2-server` | **21** | `88` | `67` | `8` | `38.1%` |
| `grpc-java` | **28** | `184` | `187` | `15` | `53.6%` |
| `hadoop` | **6** | `46` | `65` | `1` | `16.7%` |
| `hbase` | **21** | `175` | `163` | `17` | `81.0%` |
| `hibernate-orm` | **13** | `63` | `59` | `4` | `30.8%` |
| `jdk11u-dev` | **10** | `95` | `68` | `2` | `20.0%` |
| `jdk17u-dev` | **59** | `434` | `487` | `10` | `16.9%` |
| `jdk21u-dev` | **54** | `391` | `486` | `13` | `24.1%` |
| `jdk25u-dev` | **26** | `195` | `192` | `7` | `26.9%` |
| `logstash` | **3** | `5` | `5` | `3` | `100.0%` |
| `spring-framework` | **9** | `25` | `103` | `0` | `0.0%` |
| `sql` | **13** | `136` | `104` | `5` | `38.5%` |

---

## ⚡ Success Pathways Distribution

We classify successful backports into **four distinct execution pathways** depending on LLM synthesis requirements, standard validator retry loop engagement, or fallback agent intervention.

| Success Pathway | Successful Runs | % of Successes | Pathway Description |
| :--- | :---: | :---: | :--- |
| ⚡ **Fast Apply Success** | `309` | `72.9%` | Applied successfully on disk immediately without LLM synthesis or retries. |
| 🧠 **First Try Synthesis Success** | `68` | `16.0%` | Synthesis required, but succeeded on the very first validation attempt (no retries). |
| 🔄 **Standard Retry Success** | `13` | `3.1%` | Succeeded after standard validator retry loops (fixing syntax or compiling errors). |
| 🛡️ **Fallback Recovery Success** | `34` | `8.0%` | Standard path failed entirely, successfully recovered by engaging Fallback Agent. |
| **Total Successes** | **424** | **100.0%** | Combined success rate: **424/490 (86.53%)** |

### Success Pathways Progress
* **Fast Apply Success:** `[##################-------]`
* **First Try Synthesis Success:** `[####---------------------]`
* **Standard Retry Success:** `[-------------------------]`
* **Fallback Recovery Success:** `[##-----------------------]`

---

### 📦 Success Pathways by Repository

| Repository | Fast Apply | First Try Synthesis | Standard Retry | Fallback Recovery | Total Successes |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `crate` | `84` | `16` | `3` | `11` | **114** |
| `druid` | `3` | `3` | `0` | `0` | **6** |
| `elasticsearch` | `62` | `4` | `7` | `7` | **80** |
| `graylog2-server` | `10` | `1` | `1` | `1` | **13** |
| `grpc-java` | `23` | `2` | `1` | `0` | **26** |
| `hadoop` | `2` | `1` | `0` | `2` | **5** |
| `hbase` | `13` | `3` | `0` | `2` | **18** |
| `hibernate-orm` | `4` | `2` | `0` | `3` | **9** |
| `jdk11u-dev` | `3` | `3` | `0` | `0` | **6** |
| `jdk17u-dev` | `33` | `21` | `0` | `0` | **54** |
| `jdk21u-dev` | `36` | `8` | `1` | `3` | **48** |
| `jdk25u-dev` | `24` | `2` | `0` | `0` | **26** |
| `logstash` | `3` | `0` | `0` | `0` | **3** |
| `spring-framework` | `8` | `0` | `0` | `1` | **9** |
| `sql` | `1` | `2` | `0` | `4` | **7** |

---

## ⏱️ Cumulative Execution Time Distribution Matrix (Successful Runs)

Cumulative execution time represents the wall-clock duration of a successful run, aggregating baseline AI synthesis time, build and validation compilation times, standard validator retry loops, and fallback agent execution times.

### 📊 Pathway Execution Time Statistics

| Success Pathway | Count | Average Total Time | Median Total Time | Min / Max Time |
| :--- | :---: | :---: | :---: | :---: |
| ⚡ **Fast Apply Success** | `309` | `108.27s` | `55.00s` | `8.89s / 552.94s` |
| 🧠 **First Try Synthesis Success** | `68` | `145.79s` | `86.39s` | `12.00s / 796.78s` |
| 🔄 **Standard Retry Success** | `13` | `181.73s` | `101.82s` | `16.68s / 705.86s` |
| 🛡️ **Fallback Recovery Success** | `34` | `366.30s` | `243.16s` | `53.43s / 1001.40s` |

### 🏢 Repository-wise Average Cumulative Time Matrix

| Repository | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
| `crate` | `260.97s` | `332.15s` | `468.83s` | `711.40s` |
| `druid` | `33.06s` | `51.12s` | `-` | `-` |
| `elasticsearch` | `70.88s` | `73.33s` | `98.01s` | `219.26s` |
| `graylog2-server` | `10.49s` | `12.00s` | `16.68s` | `53.43s` |
| `grpc-java` | `34.52s` | `35.10s` | `36.73s` | `-` |
| `hadoop` | `43.75s` | `51.93s` | `-` | `245.95s` |
| `hbase` | `49.16s` | `109.81s` | `-` | `187.41s` |
| `hibernate-orm` | `23.94s` | `31.04s` | `-` | `294.13s` |
| `jdk11u-dev` | `54.27s` | `88.09s` | `-` | `-` |
| `jdk17u-dev` | `53.84s` | `104.43s` | `-` | `-` |
| `jdk21u-dev` | `53.49s` | `100.84s` | `216.60s` | `212.76s` |
| `jdk25u-dev` | `53.62s` | `157.69s` | `-` | `-` |
| `logstash` | `17.82s` | `-` | `-` | `-` |
| `spring-framework` | `12.60s` | `-` | `-` | `165.06s` |
| `sql` | `12.71s` | `23.89s` | `-` | `122.05s` |


### 🏷️ Patch Type-wise Average Cumulative Time Matrix

| Patch Type | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
| `TYPE-I` | `102.00s` | `119.30s` | `36.73s` | `324.20s` |
| `TYPE-II` | `120.37s` | `142.11s` | `54.52s` | `479.01s` |
| `TYPE-III` | `-` | `152.44s` | `-` | `201.39s` |
| `TYPE-IV` | `-` | `309.42s` | `705.86s` | `-` |
| `TYPE-V` | `86.15s` | `140.02s` | `182.05s` | `388.02s` |


---

## 🪙 LLM Token Usage Distribution Matrix (Successful Runs)

This section maps the LLM token consumption distributions (sum of input and output tokens across all agent execution phases, including fallback agents when engaged) across different success pathways.

### 📊 Pathway Token Usage Statistics

| Success Pathway | Count | Average Tokens | Median Tokens | Min / Max Tokens |
| :--- | :---: | :---: | :---: | :---: |
| ⚡ **Fast Apply Success** | `309` | `0` | `0` | `0 / 0` |
| 🧠 **First Try Synthesis Success** | `68` | `4,107` | `3,565` | `0 / 18,822` |
| 🔄 **Standard Retry Success** | `13` | `1,468` | `0` | `0 / 19,086` |
| 🛡️ **Fallback Recovery Success** | `34` | `45,945` | `24,014` | `846 / 166,545` |

### 🏢 Repository-wise Average Token Usage Matrix

| Repository | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
| `crate` | `0` | `163` | `0` | `46,571` |
| `druid` | `0` | `3,503` | `-` | `-` |
| `elasticsearch` | `0` | `0` | `0` | `4,970` |
| `graylog2-server` | `0` | `0` | `0` | `1,754` |
| `grpc-java` | `0` | `0` | `0` | `-` |
| `hadoop` | `0` | `4,767` | `-` | `53,659` |
| `hbase` | `0` | `8,701` | `-` | `81,922` |
| `hibernate-orm` | `0` | `2,070` | `-` | `58,803` |
| `jdk11u-dev` | `0` | `6,232` | `-` | `-` |
| `jdk17u-dev` | `0` | `5,730` | `-` | `-` |
| `jdk21u-dev` | `0` | `7,162` | `19,086` | `105,468` |
| `jdk25u-dev` | `0` | `11,390` | `-` | `-` |
| `logstash` | `0` | `-` | `-` | `-` |
| `spring-framework` | `0` | `-` | `-` | `15,711` |
| `sql` | `0` | `6,026` | `-` | `58,406` |


### 🏷️ Patch Type-wise Average Token Usage Matrix

| Patch Type | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
| `TYPE-I` | `0` | `3,782` | `0` | `30,041` |
| `TYPE-II` | `0` | `3,782` | `0` | `58,510` |
| `TYPE-III` | `-` | `4,861` | `-` | `64,485` |
| `TYPE-IV` | `-` | `1,827` | `0` | `-` |
| `TYPE-V` | `0` | `4,722` | `2,386` | `44,520` |

---

## 🚫 List of Empty Patches (29 total)

These runs generated an empty patch file (trimmed size < 2 characters) or no patch file at all. These are treated as **failures** even if JSON records showed pass indicators.

| # | Repository | Patch ID | Baseline Status |
| :---: | :--- | :--- | :---: |
| 1 | `crate` | `TYPE-I_43de35c7` | 🔴 Fail (Correct) |
| 2 | `crate` | `TYPE-V_76cab1d4` | 🔴 Fail (Correct) |
| 3 | `crate` | `TYPE-V_a143937a` | 🔴 Fail (Correct) |
| 4 | `elasticsearch` | `TYPE-III_88cf2487` | 🔴 Fail (Correct) |
| 5 | `elasticsearch` | `TYPE-II_242b8414` | 🔴 Fail (Correct) |
| 6 | `elasticsearch` | `TYPE-II_48f87c57` | 🔴 Fail (Correct) |
| 7 | `elasticsearch` | `TYPE-II_77eb1917` | 🔴 Fail (Correct) |
| 8 | `elasticsearch` | `TYPE-II_8e3b3aa1` | 🔴 Fail (Correct) |
| 9 | `elasticsearch` | `TYPE-II_d76e1af0` | 🔴 Fail (Correct) |
| 10 | `elasticsearch` | `TYPE-I_c9cce2cf` | 🔴 Fail (Correct) |
| 11 | `elasticsearch` | `TYPE-V_2cc86b3d` | 🔴 Fail (Correct) |
| 12 | `elasticsearch` | `TYPE-V_d1644b37` | 🔴 Fail (Correct) |
| 13 | `elasticsearch` | `TYPE-V_deeeadc0` | 🔴 Fail (Correct) |
| 14 | `elasticsearch` | `TYPE-V_f3cd890f` | 🔴 Fail (Correct) |
| 15 | `graylog2-server` | `TYPE-III_fe699c8d` | 🔴 Fail (Correct) |
| 16 | `graylog2-server` | `TYPE-II_32fbea91` | 🔴 Fail (Correct) |
| 17 | `graylog2-server` | `TYPE-II_a78649d1` | 🔴 Fail (Correct) |
| 18 | `graylog2-server` | `TYPE-I_12169e59` | 🔴 Fail (Correct) |
| 19 | `graylog2-server` | `TYPE-I_f4dfb95d` | 🔴 Fail (Correct) |
| 20 | `graylog2-server` | `TYPE-V_42768151` | 🔴 Fail (Correct) |
| 21 | `grpc-java` | `TYPE-IV_55ae1d05` | 🔴 Fail (Correct) |
| 22 | `grpc-java` | `TYPE-V_d89628c3` | 🔴 Fail (Correct) |
| 23 | `hibernate-orm` | `TYPE-III_b78f80fe` | 🔴 Fail (Correct) |
| 24 | `hibernate-orm` | `TYPE-III_b8dc72cc` | 🔴 Fail (Correct) |
| 25 | `hibernate-orm` | `TYPE-V_72dae39e` | 🔴 Fail (Correct) |
| 26 | `jdk17u-dev` | `TYPE-II_f3ed2758` | 🔴 Fail (Correct) |
| 27 | `jdk21u-dev` | `TYPE-II_4ba94ef6` | 🔴 Fail (Correct) |
| 28 | `jdk21u-dev` | `TYPE-I_f3ed2758` | 🔴 Fail (Correct) |
| 29 | `jdk21u-dev` | `TYPE-V_3b582dff` | 🔴 Fail (Correct) |

---

## 📐 List of Patches with Fewer Hunks (104 total)

These successful runs achieved **hunk consolidation**, meaning the agent-generated patch had **fewer production Java hunks** than the original developer patch (`gen_hunks < dev_hunks`).

| # | Repository | Patch ID | Dev Hunks | Gen Hunks | Net Hunk Reduction | Success Status |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| 1 | `crate` | `TYPE-II_006187ad` | `8` | `7` | **-1 hunks** | 🟢 Success |
| 2 | `crate` | `TYPE-IV_3b37290a` | `9` | `1` | **-8 hunks** | 🟢 Success |
| 3 | `crate` | `TYPE-IV_d150a2e5` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 4 | `crate` | `TYPE-V_10643658` | `4` | `2` | **-2 hunks** | 🟢 Success |
| 5 | `crate` | `TYPE-V_1c52ae11` | `15` | `3` | **-12 hunks** | 🟢 Success |
| 6 | `crate` | `TYPE-V_27413adb` | `11` | `4` | **-7 hunks** | 🟢 Success |
| 7 | `crate` | `TYPE-V_e6e749eb` | `7` | `3` | **-4 hunks** | 🟢 Success |
| 8 | `elasticsearch` | `TYPE-III_110b2060` | `8` | `2` | **-6 hunks** | 🟢 Success |
| 9 | `elasticsearch` | `TYPE-II_281ee04f` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 10 | `elasticsearch` | `TYPE-II_38d9710e` | `4` | `2` | **-2 hunks** | 🟢 Success |
| 11 | `elasticsearch` | `TYPE-II_41f09bf1` | `7` | `2` | **-5 hunks** | 🟢 Success |
| 12 | `elasticsearch` | `TYPE-II_465c65c0` | `6` | `4` | **-2 hunks** | 🟢 Success |
| 13 | `elasticsearch` | `TYPE-II_5531e5dc` | `8` | `7` | **-1 hunks** | 🟢 Success |
| 14 | `elasticsearch` | `TYPE-II_7facc94b` | `14` | `4` | **-10 hunks** | 🟢 Success |
| 15 | `elasticsearch` | `TYPE-II_aba25c62` | `11` | `8` | **-3 hunks** | 🟢 Success |
| 16 | `elasticsearch` | `TYPE-I_41dae025` | `4` | `1` | **-3 hunks** | 🟢 Success |
| 17 | `elasticsearch` | `TYPE-I_43e3e24d` | `16` | `5` | **-11 hunks** | 🟢 Success |
| 18 | `elasticsearch` | `TYPE-I_45e80f55` | `7` | `3` | **-4 hunks** | 🟢 Success |
| 19 | `elasticsearch` | `TYPE-I_56452409` | `7` | `2` | **-5 hunks** | 🟢 Success |
| 20 | `elasticsearch` | `TYPE-I_7c46556e` | `10` | `9` | **-1 hunks** | 🟢 Success |
| 21 | `elasticsearch` | `TYPE-I_969cd70a` | `7` | `4` | **-3 hunks** | 🟢 Success |
| 22 | `elasticsearch` | `TYPE-I_a5118c2d` | `15` | `12` | **-3 hunks** | 🟢 Success |
| 23 | `elasticsearch` | `TYPE-I_a8958755` | `6` | `2` | **-4 hunks** | 🟢 Success |
| 24 | `elasticsearch` | `TYPE-V_187b192d` | `7` | `0` | **-7 hunks** | 🟢 Success |
| 25 | `elasticsearch` | `TYPE-V_21845ad7` | `3` | `0` | **-3 hunks** | 🟢 Success |
| 26 | `elasticsearch` | `TYPE-V_45ae0718` | `12` | `6` | **-6 hunks** | 🟢 Success |
| 27 | `elasticsearch` | `TYPE-V_5efba5b4` | `10` | `2` | **-8 hunks** | 🟢 Success |
| 28 | `elasticsearch` | `TYPE-V_734dd070` | `5` | `0` | **-5 hunks** | 🟢 Success |
| 29 | `elasticsearch` | `TYPE-V_79a82262` | `5` | `3` | **-2 hunks** | 🟢 Success |
| 30 | `elasticsearch` | `TYPE-V_884196ce` | `19` | `17` | **-2 hunks** | 🟢 Success |
| 31 | `elasticsearch` | `TYPE-V_aa959e69` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 32 | `elasticsearch` | `TYPE-V_c94c021d` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 33 | `elasticsearch` | `TYPE-V_f5e2a92a` | `8` | `2` | **-6 hunks** | 🟢 Success |
| 34 | `elasticsearch` | `TYPE-V_fda7fc71` | `3` | `0` | **-3 hunks** | 🟢 Success |
| 35 | `graylog2-server` | `TYPE-II_181399cf` | `8` | `6` | **-2 hunks** | 🟢 Success |
| 36 | `grpc-java` | `TYPE-I_f9b6e5f9` | `6` | `2` | **-4 hunks** | 🟢 Success |
| 37 | `hbase` | `TYPE-I_449c446c` | `11` | `10` | **-1 hunks** | 🟢 Success |
| 38 | `hbase` | `TYPE-V_47d2aa53` | `19` | `18` | **-1 hunks** | 🟢 Success |
| 39 | `hibernate-orm` | `TYPE-II_5c85c1aa` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 40 | `hibernate-orm` | `TYPE-V_3c4a340c` | `6` | `2` | **-4 hunks** | 🟢 Success |
| 41 | `jdk11u-dev` | `TYPE-II_42ecc8a3` | `3` | `1` | **-2 hunks** | 🟢 Success |
| 42 | `jdk11u-dev` | `TYPE-II_b3477399` | `13` | `7` | **-6 hunks** | 🟢 Success |
| 43 | `jdk11u-dev` | `TYPE-II_cfee4512` | `9` | `4` | **-5 hunks** | 🟢 Success |
| 44 | `jdk11u-dev` | `TYPE-V_f4b140b4` | `11` | `5` | **-6 hunks** | 🟢 Success |
| 45 | `jdk17u-dev` | `TYPE-III_0259da92` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 46 | `jdk17u-dev` | `TYPE-III_81484d8c` | `5` | `4` | **-1 hunks** | 🟢 Success |
| 47 | `jdk17u-dev` | `TYPE-III_bfaf5704` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 48 | `jdk17u-dev` | `TYPE-III_d44aaa37` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 49 | `jdk17u-dev` | `TYPE-II_169a5d48` | `5` | `3` | **-2 hunks** | 🟢 Success |
| 50 | `jdk17u-dev` | `TYPE-II_3ccb3c0e` | `8` | `6` | **-2 hunks** | 🟢 Success |
| 51 | `jdk17u-dev` | `TYPE-II_7765942a` | `12` | `7` | **-5 hunks** | 🟢 Success |
| 52 | `jdk17u-dev` | `TYPE-II_9f98136c` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 53 | `jdk17u-dev` | `TYPE-II_a5ffa079` | `28` | `19` | **-9 hunks** | 🟢 Success |
| 54 | `jdk17u-dev` | `TYPE-II_d55d7e8d` | `7` | `5` | **-2 hunks** | 🟢 Success |
| 55 | `jdk17u-dev` | `TYPE-II_dcd46501` | `41` | `28` | **-13 hunks** | 🟢 Success |
| 56 | `jdk17u-dev` | `TYPE-II_ded6a813` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 57 | `jdk17u-dev` | `TYPE-I_1e4eafb4` | `5` | `4` | **-1 hunks** | 🟢 Success |
| 58 | `jdk17u-dev` | `TYPE-I_3d9dc8f8` | `6` | `3` | **-3 hunks** | 🟢 Success |
| 59 | `jdk17u-dev` | `TYPE-I_42ecc8a3` | `3` | `1` | **-2 hunks** | 🟢 Success |
| 60 | `jdk17u-dev` | `TYPE-I_5cacf212` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 61 | `jdk17u-dev` | `TYPE-I_8198807b` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 62 | `jdk17u-dev` | `TYPE-I_a183bfb4` | `15` | `9` | **-6 hunks** | 🟢 Success |
| 63 | `jdk17u-dev` | `TYPE-I_c7c6d47a` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 64 | `jdk17u-dev` | `TYPE-I_cfee4512` | `9` | `4` | **-5 hunks** | 🟢 Success |
| 65 | `jdk17u-dev` | `TYPE-I_f608e81a` | `23` | `22` | **-1 hunks** | 🟢 Success |
| 66 | `jdk17u-dev` | `TYPE-V_1ec64811` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 67 | `jdk17u-dev` | `TYPE-V_47c10694` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 68 | `jdk17u-dev` | `TYPE-V_925d8293` | `6` | `5` | **-1 hunks** | 🟢 Success |
| 69 | `jdk17u-dev` | `TYPE-V_f4b140b4` | `6` | `5` | **-1 hunks** | 🟢 Success |
| 70 | `jdk21u-dev` | `TYPE-III_b0ac633b` | `32` | `25` | **-7 hunks** | 🟢 Success |
| 71 | `jdk21u-dev` | `TYPE-II_bddcd086` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 72 | `jdk21u-dev` | `TYPE-II_d5c6158c` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 73 | `jdk21u-dev` | `TYPE-II_d9e7b7e7` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 74 | `jdk21u-dev` | `TYPE-I_0259da92` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 75 | `jdk21u-dev` | `TYPE-I_47c10694` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 76 | `jdk21u-dev` | `TYPE-I_80edd5c2` | `14` | `12` | **-2 hunks** | 🟢 Success |
| 77 | `jdk21u-dev` | `TYPE-I_81484d8c` | `5` | `4` | **-1 hunks** | 🟢 Success |
| 78 | `jdk21u-dev` | `TYPE-I_819f3d6f` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 79 | `jdk21u-dev` | `TYPE-I_9f98136c` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 80 | `jdk21u-dev` | `TYPE-I_a26f7c03` | `18` | `12` | **-6 hunks** | 🟢 Success |
| 81 | `jdk21u-dev` | `TYPE-I_a9cb120d` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 82 | `jdk21u-dev` | `TYPE-I_bfaf5704` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 83 | `jdk21u-dev` | `TYPE-I_c7c6d47a` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 84 | `jdk21u-dev` | `TYPE-I_cd3a6075` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 85 | `jdk21u-dev` | `TYPE-I_d44aaa37` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 86 | `jdk21u-dev` | `TYPE-I_d55d7e8d` | `7` | `5` | **-2 hunks** | 🟢 Success |
| 87 | `jdk21u-dev` | `TYPE-I_e7026465` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 88 | `jdk21u-dev` | `TYPE-V_6af0af59` | `29` | `20` | **-9 hunks** | 🟢 Success |
| 89 | `jdk21u-dev` | `TYPE-V_fc989986` | `10` | `9` | **-1 hunks** | 🟢 Success |
| 90 | `jdk25u-dev` | `TYPE-II_35dabb1a` | `56` | `53` | **-3 hunks** | 🟢 Success |
| 91 | `jdk25u-dev` | `TYPE-II_376d77e8` | `5` | `4` | **-1 hunks** | 🟢 Success |
| 92 | `jdk25u-dev` | `TYPE-I_12e6a0b6` | `7` | `6` | **-1 hunks** | 🟢 Success |
| 93 | `jdk25u-dev` | `TYPE-I_2f2acb2e` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 94 | `jdk25u-dev` | `TYPE-I_37b725d9` | `4` | `3` | **-1 hunks** | 🟢 Success |
| 95 | `jdk25u-dev` | `TYPE-I_6f8d07ae` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 96 | `jdk25u-dev` | `TYPE-I_81985d42` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 97 | `jdk25u-dev` | `TYPE-I_85331943` | `11` | `8` | **-3 hunks** | 🟢 Success |
| 98 | `jdk25u-dev` | `TYPE-I_8d73fe91` | `2` | `1` | **-1 hunks** | 🟢 Success |
| 99 | `jdk25u-dev` | `TYPE-I_8ea544c3` | `9` | `8` | **-1 hunks** | 🟢 Success |
| 100 | `jdk25u-dev` | `TYPE-I_99829950` | `14` | `12` | **-2 hunks** | 🟢 Success |
| 101 | `jdk25u-dev` | `TYPE-I_bcff857b` | `6` | `5` | **-1 hunks** | 🟢 Success |
| 102 | `jdk25u-dev` | `TYPE-I_ced3f13f` | `3` | `2` | **-1 hunks** | 🟢 Success |
| 103 | `jdk25u-dev` | `TYPE-I_da0d9598` | `7` | `4` | **-3 hunks** | 🟢 Success |
| 104 | `sql` | `TYPE-V_d1ffabd5` | `15` | `13` | **-2 hunks** | 🟢 Success |

---

## ❌ List of Failed Patches (66 total)

These runs did not pass final validation. They failed during either fast-apply, LLM synthesis, syntax checking, compilation, or test suites validation.

| # | Repository | Patch ID | Patch Type | Failure Reason / Category |
| :---: | :--- | :--- | :---: | :--- |
| 1 | `crate` | `TYPE-III_adf9854b` | `TYPE-III` | `unknown` |
| 2 | `crate` | `TYPE-I_43de35c7` | `TYPE-I` | `unknown` |
| 3 | `crate` | `TYPE-I_d95ae1e5` | `TYPE-I` | `api_mismatch` |
| 4 | `crate` | `TYPE-V_091d3a3d` | `TYPE-V` | `api_mismatch` |
| 5 | `crate` | `TYPE-V_1773a41e` | `TYPE-V` | `api_mismatch` |
| 6 | `crate` | `TYPE-V_1bdffa59` | `TYPE-V` | `api_mismatch` |
| 7 | `crate` | `TYPE-V_28f8a4b4` | `TYPE-V` | `api_mismatch` |
| 8 | `crate` | `TYPE-V_30abc0f9` | `TYPE-V` | `api_mismatch` |
| 9 | `crate` | `TYPE-V_3d3bf842` | `TYPE-V` | `api_mismatch` |
| 10 | `crate` | `TYPE-V_76cab1d4` | `TYPE-V` | `unknown` |
| 11 | `crate` | `TYPE-V_a143937a` | `TYPE-V` | `api_mismatch` |
| 12 | `crate` | `TYPE-V_b9c42c9b` | `TYPE-V` | `api_mismatch` |
| 13 | `crate` | `TYPE-V_bb4205db` | `TYPE-V` | `api_mismatch` |
| 14 | `druid` | `TYPE-V_074944e0` | `TYPE-V` | `context_mismatch` |
| 15 | `elasticsearch` | `TYPE-III_88cf2487` | `TYPE-III` | `unknown` |
| 16 | `elasticsearch` | `TYPE-II_242b8414` | `TYPE-II` | `unknown` |
| 17 | `elasticsearch` | `TYPE-II_48f87c57` | `TYPE-II` | `unknown` |
| 18 | `elasticsearch` | `TYPE-II_77eb1917` | `TYPE-II` | `unknown` |
| 19 | `elasticsearch` | `TYPE-II_7ac25007` | `TYPE-II` | `api_mismatch` |
| 20 | `elasticsearch` | `TYPE-II_8e3b3aa1` | `TYPE-II` | `unknown` |
| 21 | `elasticsearch` | `TYPE-II_d76e1af0` | `TYPE-II` | `unknown` |
| 22 | `elasticsearch` | `TYPE-I_0fabaf77` | `TYPE-I` | `unknown` |
| 23 | `elasticsearch` | `TYPE-I_c9cce2cf` | `TYPE-I` | `unknown` |
| 24 | `elasticsearch` | `TYPE-V_2cc86b3d` | `TYPE-V` | `unknown` |
| 25 | `elasticsearch` | `TYPE-V_d1644b37` | `TYPE-V` | `unknown` |
| 26 | `elasticsearch` | `TYPE-V_deeeadc0` | `TYPE-V` | `unknown` |
| 27 | `elasticsearch` | `TYPE-V_f3cd890f` | `TYPE-V` | `unknown` |
| 28 | `graylog2-server` | `TYPE-III_fe699c8d` | `TYPE-III` | `api_mismatch` |
| 29 | `graylog2-server` | `TYPE-II_32fbea91` | `TYPE-II` | `unknown` |
| 30 | `graylog2-server` | `TYPE-II_a78649d1` | `TYPE-II` | `unknown` |
| 31 | `graylog2-server` | `TYPE-I_12169e59` | `TYPE-I` | `unknown` |
| 32 | `graylog2-server` | `TYPE-I_f4dfb95d` | `TYPE-I` | `unknown` |
| 33 | `graylog2-server` | `TYPE-V_42768151` | `TYPE-V` | `unknown` |
| 34 | `graylog2-server` | `TYPE-V_45e5c07e` | `TYPE-V` | `api_mismatch` |
| 35 | `graylog2-server` | `TYPE-V_4a1cbb4d` | `TYPE-V` | `api_mismatch` |
| 36 | `grpc-java` | `TYPE-IV_55ae1d05` | `TYPE-IV` | `unknown` |
| 37 | `grpc-java` | `TYPE-V_d89628c3` | `TYPE-V` | `context_mismatch` |
| 38 | `hadoop` | `TYPE-II_7504b850` | `TYPE-II` | `unknown` |
| 39 | `hbase` | `TYPE-I_78b06cef` | `TYPE-I` | `api_mismatch` |
| 40 | `hbase` | `TYPE-I_7ef359b7` | `TYPE-I` | `api_mismatch` |
| 41 | `hbase` | `TYPE-I_8c989c92` | `TYPE-I` | `api_mismatch` |
| 42 | `hibernate-orm` | `TYPE-III_b78f80fe` | `TYPE-III` | `unknown` |
| 43 | `hibernate-orm` | `TYPE-III_b8dc72cc` | `TYPE-III` | `unknown` |
| 44 | `hibernate-orm` | `TYPE-V_6cfdc641` | `TYPE-V` | `api_mismatch` |
| 45 | `hibernate-orm` | `TYPE-V_72dae39e` | `TYPE-V` | `unknown` |
| 46 | `jdk11u-dev` | `TYPE-II_2fcb8168` | `TYPE-II` | `infrastructure` |
| 47 | `jdk11u-dev` | `TYPE-V_158b93d1` | `TYPE-V` | `api_mismatch` |
| 48 | `jdk11u-dev` | `TYPE-V_4d2cd26a` | `TYPE-V` | `context_mismatch` |
| 49 | `jdk11u-dev` | `TYPE-V_a26f7c03` | `TYPE-V` | `api_mismatch` |
| 50 | `jdk17u-dev` | `TYPE-III_a26f7c03` | `TYPE-III` | `api_mismatch` |
| 51 | `jdk17u-dev` | `TYPE-II_f3ed2758` | `TYPE-II` | `unknown` |
| 52 | `jdk17u-dev` | `TYPE-V_268ec61d` | `TYPE-V` | `api_mismatch` |
| 53 | `jdk17u-dev` | `TYPE-V_2836c34b` | `TYPE-V` | `api_mismatch` |
| 54 | `jdk17u-dev` | `TYPE-V_3b582dff` | `TYPE-V` | `api_mismatch` |
| 55 | `jdk21u-dev` | `TYPE-II_4ba94ef6` | `TYPE-II` | `unknown` |
| 56 | `jdk21u-dev` | `TYPE-I_10335f60` | `TYPE-I` | `unknown` |
| 57 | `jdk21u-dev` | `TYPE-I_f3ed2758` | `TYPE-I` | `unknown` |
| 58 | `jdk21u-dev` | `TYPE-V_158b93d1` | `TYPE-V` | `api_mismatch` |
| 59 | `jdk21u-dev` | `TYPE-V_3b582dff` | `TYPE-V` | `unknown` |
| 60 | `jdk21u-dev` | `TYPE-V_720b4464` | `TYPE-V` | `api_mismatch` |
| 61 | `sql` | `TYPE-III_774a3a23` | `TYPE-III` | `unknown` |
| 62 | `sql` | `TYPE-V_0b4423e9` | `TYPE-V` | `unknown` |
| 63 | `sql` | `TYPE-V_284ecc49` | `TYPE-V` | `unknown` |
| 64 | `sql` | `TYPE-V_42c13b40` | `unknown` | `unknown` |
| 65 | `sql` | `TYPE-V_69b9e82b` | `TYPE-V` | `unknown` |
| 66 | `sql` | `TYPE-V_6c3efa14` | `TYPE-V` | `unknown` |

---
*Dashboard Report Generated: 2026-05-19 12:25:45 (Local Time)*
