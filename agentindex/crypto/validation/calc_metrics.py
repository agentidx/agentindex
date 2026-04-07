# All errors from our backtests (percentage points)
# FTX (13 tokens): 1.0, 7.2, 2.1, 12.4, 3.7, 8.3, 15.4, 14.7, 8.5, 11.6, 17.0, 16.5, 3.7
ftx = [1.0, 7.2, 2.1, 12.4, 3.7, 8.3, 15.4, 14.7, 8.5, 11.6, 17.0, 16.5, 3.7]
# LUNA (13): 7.2, 0.0, 16.9, 1.5, 12.5, 5.5, 4.4, 22.2, 11.3, 6.4, 16.7, 16.7, 12.8
luna = [7.2, 0.0, 16.9, 1.5, 12.5, 5.5, 4.4, 22.2, 11.3, 6.4, 16.7, 16.7, 12.8]
# 3AC (13): 7.0, 9.4, 6.5, 3.0, 0.9, 11.9, 1.6, 4.3, 1.1, 5.0, 8.3, 4.1, 3.7
ac3 = [7.0, 9.4, 6.5, 3.0, 0.9, 11.9, 1.6, 4.3, 1.1, 5.0, 8.3, 4.1, 3.7]
# BTC bear (13): 21.7, 29.0, 38.1, 19.0, 29.2, 25.6, 30.7, 28.8, 30.5, 28.9, 27.0, 17.8, 1.8
bear = [21.7, 29.0, 38.1, 19.0, 29.2, 25.6, 30.7, 28.8, 30.5, 28.9, 27.0, 17.8, 1.8]
# Flash Oct 2025 (19): 0.0, 5.9, 6.8, 12.2, 15.9, 25.0, 9.6, 24.4, 11.9, 8.0, 5.7, 9.2, 45.5, 17.1, 23.9, 4.3, 40.6, 21.7, 10.5
flash = [0.0, 5.9, 6.8, 12.2, 15.9, 25.0, 9.6, 24.4, 11.9, 8.0, 5.7, 9.2, 45.5, 17.1, 23.9, 4.3, 40.6, 21.7, 10.5]

all_errors = ftx + luna + ac3 + bear + flash
# Exclude BTC bear (prolonged, not comparable)
short_term = ftx + luna + ac3 + flash

print("=== ALL 5 CRISES (71 pairs) ===")
print(f"Mean: {sum(all_errors)/len(all_errors):.1f}pp")
print(f"Median: {sorted(all_errors)[len(all_errors)//2]:.1f}pp")
print(f"Within 5pp: {sum(1 for e in all_errors if e <= 5)}/{len(all_errors)} ({sum(1 for e in all_errors if e <= 5)/len(all_errors)*100:.0f}%)")
print(f"Within 10pp: {sum(1 for e in all_errors if e <= 10)}/{len(all_errors)} ({sum(1 for e in all_errors if e <= 10)/len(all_errors)*100:.0f}%)")
print(f"Within 15pp: {sum(1 for e in all_errors if e <= 15)}/{len(all_errors)} ({sum(1 for e in all_errors if e <= 15)/len(all_errors)*100:.0f}%)")

print("\n=== 4 SHORT-TERM CRISES (58 pairs, excl prolonged bear) ===")
print(f"Mean: {sum(short_term)/len(short_term):.1f}pp")
print(f"Median: {sorted(short_term)[len(short_term)//2]:.1f}pp")
print(f"Within 5pp: {sum(1 for e in short_term if e <= 5)}/{len(short_term)} ({sum(1 for e in short_term if e <= 5)/len(short_term)*100:.0f}%)")
print(f"Within 10pp: {sum(1 for e in short_term if e <= 10)}/{len(short_term)} ({sum(1 for e in short_term if e <= 10)/len(short_term)*100:.0f}%)")
print(f"Within 15pp: {sum(1 for e in short_term if e <= 15)}/{len(short_term)} ({sum(1 for e in short_term if e <= 15)/len(short_term)*100:.0f}%)")

print("\n=== PER SCENARIO (short-term only) ===")
for name, errs in [("FTX", ftx), ("LUNA", luna), ("3AC", ac3), ("Flash Oct25", flash)]:
    print(f"{name:>12}: MAE {sum(errs)/len(errs):.1f}pp | Median {sorted(errs)[len(errs)//2]:.1f}pp | Within 10pp: {sum(1 for e in errs if e<=10)}/{len(errs)}")
