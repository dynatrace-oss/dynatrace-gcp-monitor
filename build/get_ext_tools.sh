EXT_DIR=ext_tools


get_ext() {
URL=$1
NAME=$2

shift 2

while [ "$#" -ge 2 ]
do
   ARCH_SRC=$1
   ARCH_DST=$2

   FILE="$EXT_DIR/${NAME}_${ARCH_DST}"
   wget -v "${URL}${ARCH_SRC}" -O "$FILE" && chmod +x "$FILE"
   shift 2
done
}

get_ext https://github.com/stedolan/jq/releases/download/jq-1.6/jq jq -linux64 linux_x64

get_ext https://github.com/mikefarah/yq/releases/download/v4.9.8/yq yq _linux_amd64 linux_x64