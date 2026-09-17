#!/usr/bin/env bash
# Renders charts/src/[0-9]*.puml into charts/svg/ and charts/png/ with a pinned PlantUML jar.
# Needs only Java (no Graphviz: diagrams use PlantUML's built-in Smetana layout).
set -euo pipefail
cd "$(dirname "$0")"

VERSION="1.2026.8"
SHA256="5e1ecfa8ecd32c90b03bbf3b1eb6f020943f98ab0fcf4032be31a0002ee2c462"
JAR=".tools/plantuml-${VERSION}.jar"

if [[ ! -f "$JAR" ]]; then
  mkdir -p .tools
  echo "Downloading PlantUML ${VERSION}..."
  curl -fsSL -o "${JAR}.part" \
    "https://github.com/plantuml/plantuml/releases/download/v${VERSION}/plantuml-${VERSION}.jar"
  echo "${SHA256}  ${JAR}.part" | sha256sum -c --quiet -
  mv "${JAR}.part" "$JAR"
fi

mkdir -p svg png
# -failfast2: check all sources for syntax errors first and stop instead of rendering error images.
# -o is relative to each source file's directory (src/).
java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=16384 -jar "$JAR" -failfast2 -charset UTF-8 -tsvg -o ../svg src/[0-9]*.puml
java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=16384 -jar "$JAR" -failfast2 -charset UTF-8 -tpng -o ../png src/[0-9]*.puml

echo "Rendered $(ls svg/*.svg | wc -l) SVG and $(ls png/*.png | wc -l) PNG files."
