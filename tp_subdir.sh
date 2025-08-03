#!/bin/bash

# 设置基础目录
BASE_DIR="/volume1/strm/emby/emby/misc/日韩剧集【24T】"
DEST_DIR="/volume1/strm/emby/ln2entv"

# 检查基础目录是否存在
if [ ! -d "$BASE_DIR" ]; then
    echo "错误: 目录 '$BASE_DIR' 不存在"
    exit 1
fi

# 检查 tp.py 是否存在
if [ ! -f "tp.py" ]; then
    echo "错误: tp.py 文件不存在于当前目录"
    exit 1
fi

echo "开始处理目录: $BASE_DIR"
echo "=========================================="

# 计数器
count=0
success_count=0
error_count=0

# 遍历基础目录下的所有子目录
for subdir in "$BASE_DIR"/*; do
    # 检查是否为目录
    if [ -d "$subdir" ]; then
        count=$((count + 1))
        subdir_name=$(basename "$subdir")

        echo "[$count] 正在处理: $subdir_name"
        echo "完整路径: $subdir"

        # 运行 python 脚本
        python /volume1/strm/torcp/tp.py "$subdir" -d "$DEST_DIR" --tmdb-api-key='c6ad5065ed9062cf3e605feb9e03b41e' --emby-bracket --origin-name --sep-area5 --tv
        echo "✅ 成功处理: $subdir_name"
        success_count=$((success_count + 1))

        echo "------------------------------------------"
    fi
done

echo "=========================================="
echo "处理完成！"
echo "总计处理目录数: $count"
echo "成功处理: $success_count"
echo "处理失败: $error_count"

# 如果有错误，以非零状态码退出
if [ $error_count -gt 0 ]; then
    exit 1
fi