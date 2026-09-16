#!/bin/bash
# Incremental exporter v2: code+docs on the working branch; finished media
# on the 'production-outcomes' orphan branch (files <95MB as-is, bigger
# ones split into 90MB chunks: `cat name.mp4.part* > name.mp4`).
set -u
cd /workspace/text-to-video
LOG(){ echo "[export $(date +%H:%M:%S)] $*"; }
cp /workspace/IMPROVEMENTS.md docs/IMPROVEMENTS.md 2>/dev/null
git add -A scripts/ docs/ series/*/episodes/ series/*/bible.json CLAUDE.md 2>/dev/null
git commit -q -m "Improvement loop: incremental export $(date +%Y%m%d-%H%M)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" 2>/dev/null && LOG "code committed" || LOG "code: nothing new"
if git push -q origin HEAD > /tmp/export_push_code.txt 2>&1; then LOG "code pushed"; else LOG "code push FAILED: $(tail -1 /tmp/export_push_code.txt)"; fi

EXP=/workspace/media_export
MANIFEST=/workspace/exports_manifest.txt
touch $MANIFEST
if [ ! -d $EXP ]; then
  mkdir -p $EXP
  cd $EXP
  git init -q .
  git remote add origin git@github.com:jmyth742/animation-creator.git
  git checkout -q --orphan production-outcomes
  git config user.name "Developer"; git config user.email "dev@text-to-video.local"
  echo "# Tir na nOg — production outcomes (rolling export)" > README.md
  echo "Large files are split: reassemble with 'cat name.mp4.part* > name.mp4'" >> README.md
  git add README.md && git commit -q -m "init outcomes branch"
  cd /workspace/text-to-video
fi
cd $EXP
git config user.name > /dev/null 2>&1 || { git config user.name "Developer"; git config user.email "dev@text-to-video.local"; }
CHANGED=0
for f in /workspace/review/*.mp4 /workspace/review/*.png /workspace/review/*.srt; do
  [ -f "$f" ] || continue
  SUM=$(md5sum "$f" | cut -d' ' -f1); BN=$(basename "$f")
  grep -q "$SUM  $BN" $MANIFEST && continue
  SIZE=$(stat -c%s "$f")
  if [ "$SIZE" -gt 95000000 ]; then
    rm -f "$BN".part*
    split -b 90M "$f" "$BN.part"
  else
    cp "$f" .
  fi
  echo "$SUM  $BN" >> $MANIFEST
  CHANGED=1
  LOG "staged $BN"
done
if [ "$CHANGED" = 1 ]; then
  git add -A .
  git commit -q -m "media export $(date +%Y%m%d-%H%M)" || LOG "media commit FAILED (identity? nothing staged?)"
  # NOTE: never -f here — the branch history is the archive; and check git's status, not tail's
  if git push -q origin production-outcomes > /tmp/export_push.txt 2>&1; then LOG "media pushed"; else LOG "media push FAILED: $(tail -1 /tmp/export_push.txt)"; fi
else
  LOG "media: nothing new"
fi
LOG "export pass complete"
