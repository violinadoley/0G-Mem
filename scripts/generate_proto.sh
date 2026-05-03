#!/usr/bin/env bash
# Generate Python gRPC stubs from proto/disperser.proto
# Run: make proto  OR  bash scripts/generate_proto.sh

set -e

PROTO_DIR="proto"
OUT_DIR="proto"

echo "Generating gRPC stubs from $PROTO_DIR/disperser.proto..."

python -m grpc_tools.protoc \
  -I "$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR/disperser.proto"

# Fix import path in generated grpc file
sed -i '' 's/^import disperser_pb2/from proto import disperser_pb2/' \
  "$OUT_DIR/disperser_pb2_grpc.py" 2>/dev/null || \
sed -i 's/^import disperser_pb2/from proto import disperser_pb2/' \
  "$OUT_DIR/disperser_pb2_grpc.py"

echo "Done. Generated:"
echo "  $OUT_DIR/disperser_pb2.py"
echo "  $OUT_DIR/disperser_pb2_grpc.py"
