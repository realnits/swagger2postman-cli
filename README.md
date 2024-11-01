# Swagger to Postman Converter 🔄

Convert Swagger/OpenAPI docs to organized Postman collections with just one command! Keeps your API structure clean and supports multiple auth headers.

## 🚀 Quick Start

1. Make sure you have Python 3.7+ installed
2. Install required package:
```bash
pip install requests
```

3. Run the converter:
```bash
# Basic usage
python swagger_to_postman.py --url https://api.example.com/swagger.json

# With auth headers
python swagger_to_postman.py \
  --url https://api.example.com/swagger.json \
  --header "Authorization:Bearer your-token" \
  --header "ApiKey:your-key"
```

## 📋 Command Options

```bash
--url      # Swagger URL (required)
--header   # Add headers (key:value format)
--output   # Output filename (default: postman_collection.json)
```

## ✨ What You Get

- Organized folders matching your Swagger structure
- Working request examples with proper headers
- Query params and path variables preserved
- Example request bodies included

## 🔍 Example

```bash
# Real-world example
python swagger_to_postman.py \
  --url https://api.company.com/swagger.json \
  --header "Authorization:Bearer token123" \
  --output my-api.json
```

## 🆘 Common Issues

1. **Can't connect to URL?**
   - Check if the URL is accessible
   - Make sure you're on the right network/VPN

2. **Header not working?**
   - Use correct format: `"key:value"`
   - Example: `"Authorization:Bearer token"`

3. **Invalid JSON error?**
   - Verify the URL returns valid Swagger JSON
   - Check if you need auth headers to access it

## 🤝 Need Help?

Create an issue in the repository with:
- The command you ran
- The error message you got
- Your Swagger URL (if public)

## 📝 License

MIT License - feel free to use and modify!
