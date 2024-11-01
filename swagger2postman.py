import json
import requests
import argparse
from urllib.parse import urlparse
from typing import Dict, List, Optional

class SwaggerToPostmanConverter:
    def __init__(self, swagger_url: str, headers: Dict[str, str]):
        self.swagger_url = swagger_url
        self.headers = headers
        self.swagger_data = None
        
    def fetch_swagger_definition(self) -> None:
        """Fetch the Swagger definition from the URL"""
        try:
            response = requests.get(self.swagger_url, headers=self.headers)
            response.raise_for_status()
            self.swagger_data = response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch Swagger definition: {str(e)}")

    def get_base_url(self) -> str:
        """Extract base URL from Swagger definition"""
        if 'servers' in self.swagger_data:
            return self.swagger_data['servers'][0]['url']
        parsed_url = urlparse(self.swagger_url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    def generate_example_from_schema(self, schema: Dict) -> any:
        """Generate example data from JSON schema"""
        if 'type' not in schema:
            return {}
        
        if schema['type'] == 'object':
            result = {}
            if 'properties' in schema:
                for prop, prop_schema in schema['properties'].items():
                    result[prop] = self.generate_example_from_schema(prop_schema)
            return result
        
        elif schema['type'] == 'array':
            if 'items' in schema:
                return [self.generate_example_from_schema(schema['items'])]
            return []
        
        type_examples = {
            'string': "string",
            'number': 0,
            'integer': 0,
            'boolean': False
        }
        return type_examples.get(schema['type'])

    def create_request_item(self, path: str, method: str, operation: Dict, base_url: str) -> Dict:
        """Create a Postman request item from Swagger operation"""
        request = {
            "name": operation.get('summary', f"{method.upper()} {path}"),
            "request": {
                "method": method.upper(),
                "header": [{"key": k, "value": v, "type": "text"} for k, v in self.headers.items()],
                "url": {
                    "raw": f"{base_url}{path}",
                    "protocol": urlparse(base_url).scheme,
                    "host": urlparse(base_url).netloc.split('.'),
                    "path": path.split('/')[1:] if path.startswith('/') else path.split('/'),
                    "query": []
                },
                "description": operation.get('description', '')
            },
            "response": []
        }

        # Add parameters
        if 'parameters' in operation:
            for param in operation['parameters']:
                if param['in'] == 'query':
                    request['request']['url']['query'].append({
                        "key": param['name'],
                        "value": "",
                        "description": param.get('description', ''),
                        "disabled": not param.get('required', False)
                    })
                elif param['in'] == 'header':
                    request['request']['header'].append({
                        "key": param['name'],
                        "value": "",
                        "description": param.get('description', ''),
                        "disabled": not param.get('required', False)
                    })

        # Add request body if present
        if 'requestBody' in operation:
            content_type = list(operation['requestBody']['content'].keys())[0]
            schema = operation['requestBody']['content'][content_type].get('schema', {})
            
            request['request']['body'] = {
                "mode": "raw",
                "raw": json.dumps(self.generate_example_from_schema(schema), indent=2),
                "options": {
                    "raw": {
                        "language": "json" if "json" in content_type else "text"
                    }
                }
            }
            
            request['request']['header'].append({
                "key": "Content-Type",
                "value": content_type
            })

        return request

    def organize_by_tags(self, requests: List[Dict]) -> List[Dict]:
        """Organize requests by tags from Swagger"""
        tag_groups = {}
        untagged = []

        for request in requests:
            tags = request.pop('tags', None)
            if tags and tags[0] in tag_groups:
                tag_groups[tags[0]].append(request)
            elif tags:
                tag_groups[tags[0]] = [request]
            else:
                untagged.append(request)

        # Create folders for each tag
        organized_items = []
        for tag, requests in tag_groups.items():
            organized_items.append({
                "name": tag,
                "item": requests
            })

        # Add untagged requests
        if untagged:
            organized_items.append({
                "name": "Other",
                "item": untagged
            })

        return organized_items

    def convert(self) -> Dict:
        """Convert Swagger definition to Postman collection"""
        self.fetch_swagger_definition()
        base_url = self.get_base_url()
        
        # Initialize Postman collection
        postman_collection = {
            "info": {
                "name": self.swagger_data.get('info', {}).get('title', 'API Collection'),
                "description": self.swagger_data.get('info', {}).get('description', ''),
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": []
        }

        # Convert paths to requests
        requests = []
        for path, path_data in self.swagger_data.get('paths', {}).items():
            for method, operation in path_data.items():
                request = self.create_request_item(path, method, operation, base_url)
                if 'tags' in operation:
                    request['tags'] = operation['tags']
                requests.append(request)

        # Organize requests by tags
        postman_collection['item'] = self.organize_by_tags(requests)
        
        return postman_collection

def main():
    parser = argparse.ArgumentParser(description='Convert Swagger/OpenAPI definition to Postman collection')
    parser.add_argument('--url', required=True, help='Swagger JSON URL')
    parser.add_argument('--header', action='append', help='Headers in format key:value')
    parser.add_argument('--output', default='postman_collection.json', help='Output file name')
    
    args = parser.parse_args()
    
    # Parse headers
    headers = {}
    if args.header:
        for header in args.header:
            key, value = header.split(':', 1)
            headers[key.strip()] = value.strip()
    
    try:
        converter = SwaggerToPostmanConverter(args.url, headers)
        postman_collection = converter.convert()
        
        # Save to file
        with open(args.output, 'w') as f:
            json.dump(postman_collection, f, indent=2)
        
        print(f"Successfully converted Swagger to Postman collection: {args.output}")
    
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
