curl -N -i -X POST \
  'your endpoint URL' \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{
        "messages": [
          {
            "role": "user",
            "content": "こんにちは"
          }
        ]
      }'
