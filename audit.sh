#!/bin/bash
echo "============================================"
echo "  NERQ i18n FINAL AUDIT — $(date)"
echo "============================================"

LANGS="sv vi ja ar de es fr ko zh pt nl id cs th ro tr hi ru pl it da"

SAFE_PATTERNS="is based in|surveillance alliances|privacy advantage|audited.*verify|privacy claims|Serving.*users|Related Safety|Complete Your Privacy|Add a password manager|Add Antivirus Protection|alongside your|Combine these tools|comprehensive protection|Browse Categories|Safest VPNs|Most Private Apps|Recently Analyzed|What are the best alternatives|which is safer|logging practices|ownership transparency|strongest signal is|have been detected|recommended for privacy|earning a.*grade|independently measured"

HOME_PATTERNS="Is it safe to install|Is it private|Is it reliable|Is it trustworthy|What do you want to check|Trust scores for apps|Data-driven\. Free and independent|Updated daily|Check trust score|View all categories|Popular Trust Checks|Full safety report|All safety guides|All comparisons|For Developers|Add trust checks"

TOTAL_PASS=0
TOTAL_FAIL=0
HP_PASS=0; HP_FAIL=0; S1_PASS=0; S1_FAIL=0; S2_PASS=0; S2_FAIL=0; B_PASS=0; B_FAIL=0; C_PASS=0; C_FAIL=0

echo ""
echo "=== 1. HOMEPAGE ==="
for lang in $LANGS; do
    ENG=$(curl -s --max-time 5 "http://localhost:8000/$lang/" | sed 's/<script[^>]*>.*<\/script>//g' | sed 's/<style[^>]*>.*<\/style>//g' | sed 's/<[^>]*>//g' | grep -ciE "$HOME_PATTERNS")
    if [ "$ENG" -gt 0 ]; then
        echo "  $lang: FAIL $ENG"
        HP_FAIL=$((HP_FAIL + 1)); TOTAL_FAIL=$((TOTAL_FAIL + 1))
    else
        echo "  $lang: OK"
        HP_PASS=$((HP_PASS + 1)); TOTAL_PASS=$((TOTAL_PASS + 1))
    fi
done

echo ""
echo "=== 2. /safe/nordvpn ==="
for lang in $LANGS; do
    ENG=$(curl -s --max-time 5 "http://localhost:8000/$lang/safe/nordvpn" | sed 's/<script[^>]*>.*<\/script>//g' | sed 's/<style[^>]*>.*<\/style>//g' | sed 's/<[^>]*>//g' | grep -ciE "$SAFE_PATTERNS")
    if [ "$ENG" -gt 0 ]; then
        WHICH=$(curl -s --max-time 5 "http://localhost:8000/$lang/safe/nordvpn" | sed 's/<script[^>]*>.*<\/script>//g' | sed 's/<style[^>]*>.*<\/style>//g' | sed 's/<[^>]*>//g' | grep -oiE "$SAFE_PATTERNS" | sort -u | head -3 | tr '\n' ', ')
        echo "  $lang: FAIL $ENG — $WHICH"
        S1_FAIL=$((S1_FAIL + 1)); TOTAL_FAIL=$((TOTAL_FAIL + 1))
    else
        echo "  $lang: OK"
        S1_PASS=$((S1_PASS + 1)); TOTAL_PASS=$((TOTAL_PASS + 1))
    fi
done

echo ""
echo "=== 3. /safe/express ==="
for lang in $LANGS; do
    ENG=$(curl -s --max-time 5 "http://localhost:8000/$lang/safe/express" | sed 's/<script[^>]*>.*<\/script>//g' | sed 's/<style[^>]*>.*<\/style>//g' | sed 's/<[^>]*>//g' | grep -ciE "$SAFE_PATTERNS")
    if [ "$ENG" -gt 0 ]; then
        echo "  $lang: FAIL $ENG"
        S2_FAIL=$((S2_FAIL + 1)); TOTAL_FAIL=$((TOTAL_FAIL + 1))
    else
        echo "  $lang: OK"
        S2_PASS=$((S2_PASS + 1)); TOTAL_PASS=$((TOTAL_PASS + 1))
    fi
done

echo ""
echo "=== 4. /best/safest-vpns ==="
for lang in $LANGS; do
    TITLE=$(curl -s --max-time 3 "http://localhost:8000/$lang/best/safest-vpns" | sed -n 's/.*<title>\(.*\)<\/title>.*/\1/p' | head -1)
    ENG_T=$(echo "$TITLE" | grep -ci "Safest VPNs")
    if [ "$ENG_T" -gt 0 ]; then
        echo "  $lang: FAIL English title — $TITLE"
        B_FAIL=$((B_FAIL + 1)); TOTAL_FAIL=$((TOTAL_FAIL + 1))
    else
        echo "  $lang: OK — $TITLE"
        B_PASS=$((B_PASS + 1)); TOTAL_PASS=$((TOTAL_PASS + 1))
    fi
done

echo ""
echo "=== 5. /compare/ ==="
for lang in $LANGS; do
    BODY=$(curl -s --max-time 5 "http://localhost:8000/$lang/compare/nordvpn-vs-expressvpn" | sed 's/<[^>]*>//g')
    NOT_AN=$(echo "$BODY" | grep -ci "Not Yet Analyzed")
    if [ "$NOT_AN" -gt 0 ]; then
        echo "  $lang: FAIL Not Yet Analyzed"
        C_FAIL=$((C_FAIL + 1)); TOTAL_FAIL=$((TOTAL_FAIL + 1))
    else
        echo "  $lang: OK"
        C_PASS=$((C_PASS + 1)); TOTAL_PASS=$((TOTAL_PASS + 1))
    fi
done

echo ""
echo "=== 6. TITLAR /safe/nordvpn ==="
for lang in $LANGS; do
    TITLE=$(curl -s --max-time 3 "http://localhost:8000/$lang/safe/nordvpn" | sed -n 's/.*<title>\(.*\)<\/title>.*/\1/p' | head -1 | cut -c1-70)
    echo "  $lang: $TITLE"
done

echo ""
echo "=== 7. VISIBLE TEXT sv /safe/nordvpn (30 rader) ==="
curl -s "http://localhost:8000/sv/safe/nordvpn" | sed 's/<script[^>]*>.*<\/script>//g' | sed 's/<style[^>]*>.*<\/style>//g' | sed 's/<nav[^>]*>.*<\/nav>//g' | sed 's/<footer[^>]*>.*<\/footer>//g' | sed 's/<[^>]*>//g' | sed '/^[[:space:]]*$/d' | sed 's/^[[:space:]]*//' | grep -v '^/\*\|^\*\|^body\|^a{' | head -30

echo ""
echo "============================================"
echo "  SAMMANFATTNING"
echo "  Homepage:      $HP_PASS/$((HP_PASS+HP_FAIL))"
echo "  /safe/nordvpn: $S1_PASS/$((S1_PASS+S1_FAIL))"
echo "  /safe/express: $S2_PASS/$((S2_PASS+S2_FAIL))"
echo "  /best/:        $B_PASS/$((B_PASS+B_FAIL))"
echo "  /compare/:     $C_PASS/$((C_PASS+C_FAIL))"
echo "  TOTAL: $TOTAL_PASS PASS / $TOTAL_FAIL FAIL"
echo "============================================"
