import json
import requests
import argparse
from urllib.parse import urlparse
from typing import Dict, List, Optional
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SwaggerToPostmanConverter:
    def __init__(self, swagger_url: str, headers: Dict[str, str]):
        self.swagger_url = swagger_url
        self.headers = headers
        self.swagger_data = None
        self.processed_refs = set()
        self.max_recursion_depth = 10
        self.components = {}  # Store component schemas
        self.circular_refs = set()  # Track circular references
        
    def fetch_swagger_definition(self) -> None:
        """Fetch the Swagger definition from the URL"""
        try:
            response = requests.get(self.swagger_url, headers=self.headers)
            response.raise_for_status()
            self.swagger_data = response.json()
            # Store components for reference resolution
            self.components = self.swagger_data.get('components', {}).get('schemas', {})
            if not self.components and 'definitions' in self.swagger_data:  # Support Swagger 2.0
                self.components = self.swagger_data['definitions']
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch Swagger definition: {str(e)}")

    def get_base_url(self) -> str:
        """Extract base URL from Swagger definition"""
        if 'servers' in self.swagger_data:
            return self.swagger_data['servers'][0]['url']
        parsed_url = urlparse(self.swagger_url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    def resolve_ref(self, ref: str, depth: int = 0, path: Optional[List[str]] = None) -> Dict:
        """Resolve schema reference with improved circular reference handling"""
        if path is None:
            path = []

        if depth >= self.max_recursion_depth:
            return {"type": "string", "example": f"[Max depth reached for: {ref}]"}
        
        # If we've seen this ref in the current resolution path, we have a circular reference
        if ref in path:
            self.circular_refs.add(ref)
            return {"type": "string", "example": f"[Circular reference: {ref}]"}
        
        try:
            # For Swagger 2.0 references
            if ref.startswith('#/definitions/'):
                schema_name = ref.split('/')[-1]
                if schema_name in self.components:
                    schema = self.components[schema_name]
                    if isinstance(schema, dict):
                        if '$ref' in schema:
                            return self.resolve_ref(schema['$ref'], depth + 1, path + [ref])
                        # Create a simplified version of the schema for circular references
                        return self.simplify_schema(schema, depth + 1, path + [ref])
                    return schema
            
            # For OpenAPI 3.0 references
            elif ref.startswith('#/components/schemas/'):
                schema_name = ref.split('/')[-1]
                if schema_name in self.components:
                    schema = self.components[schema_name]
                    if isinstance(schema, dict):
                        if '$ref' in schema:
                            return self.resolve_ref(schema['$ref'], depth + 1, path + [ref])
                        return self.simplify_schema(schema, depth + 1, path + [ref])
                    return schema
            
            # Handle full reference path
            ref_path = ref.split('/')
            ref_schema = self.swagger_data
            for path_part in ref_path[1:]:
                ref_schema = ref_schema[path_part]
            return self.simplify_schema(ref_schema, depth + 1, path + [ref])
            
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to resolve reference {ref}: {str(e)}")
            return {"type": "string", "example": f"[Failed to resolve: {ref}]"}

    def simplify_schema(self, schema: Dict, depth: int, path: List[str]) -> Dict:
        """Simplify schema by handling nested structures and references"""
        if not isinstance(schema, dict):
            return schema

        # For simple types, return as is
        if 'type' in schema and schema['type'] in ['string', 'number', 'integer', 'boolean']:
            return schema

        # For objects, create a simplified version
        if schema.get('type') == 'object' or 'properties' in schema:
            simplified = {'type': 'object', 'properties': {}}
            for prop_name, prop_schema in schema.get('properties', {}).items():
                if isinstance(prop_schema, dict) and '$ref' in prop_schema:
                    if prop_schema['$ref'] in path:
                        simplified['properties'][prop_name] = {
                            'type': 'string',
                            'example': f"[Circular reference to: {prop_schema['$ref']}]"
                        }
                    else:
                        simplified['properties'][prop_name] = self.resolve_ref(
                            prop_schema['$ref'], depth + 1, path
                        )
                else:
                    simplified['properties'][prop_name] = prop_schema
            return simplified

        # For arrays, simplify the items
        if schema.get('type') == 'array' and 'items' in schema:
            if isinstance(schema['items'], dict) and '$ref' in schema['items']:
                if schema['items']['$ref'] in path:
                    return {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'example': f"[Circular reference to: {schema['items']['$ref']}]"
                        }
                    }
                else:
                    return {
                        'type': 'array',
                        'items': self.resolve_ref(schema['items']['$ref'], depth + 1, path)
                    }
            return schema

        return schema

    def generate_example_from_schema(self, schema: Dict, depth: int = 0) -> any:
        """Generate example data from JSON schema with recursion protection"""
        if not schema or not isinstance(schema, dict):
            return {}

        if depth >= self.max_recursion_depth:
            return {"error": "Max recursion depth exceeded"}

        # Handle referenced schemas
        if '$ref' in schema:
            resolved_schema = self.resolve_ref(schema['$ref'])
            return self.generate_example_from_schema(resolved_schema, depth + 1)

        # Check for example or default value first
        if 'example' in schema:
            return schema['example']
        if 'default' in schema:
            return schema['default']

        schema_type = schema.get('type', 'object')
        
        # Default values for different types
        type_examples = {
            'string': schema.get('format', 'string'),
            'integer': 0,
            'number': 0.0,
            'boolean': False,
            'null': None
        }
        return type_examples.get(schema_type, '')

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
                if isinstance(param, dict) and '$ref' in param:
                    param = self.resolve_ref(param['$ref'])
                
                param_schema = param.get('schema', {})
                try:
                    example_value = self.generate_example_from_schema(param_schema) if param_schema else ""
                except Exception as e:
                    logger.warning(f"Failed to generate parameter example: {str(e)}")
                    example_value = "example"
                
                if param.get('in') == 'query':
                    request['request']['url']['query'].append({
                        "key": param['name'],
                        "value": str(example_value),
                        "description": param.get('description', ''),
                        "disabled": not param.get('required', False)
                    })
                elif param.get('in') == 'header':
                    request['request']['header'].append({
                        "key": param['name'],
                        "value": str(example_value),
                        "description": param.get('description', ''),
                        "disabled": not param.get('required', False)
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

        organized_items = []
        for tag, requests in tag_groups.items():
            organized_items.append({
                "name": tag,
                "item": requests
            })

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
        
        postman_collection = {
            "info": {
                "name": self.swagger_data.get('info', {}).get('title', 'API Collection'),
                "description": self.swagger_data.get('info', {}).get('description', ''),
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": []
        }

        requests = []
        for path, path_data in self.swagger_data.get('paths', {}).items():
            for method, operation in path_data.items():
                request = self.create_request_item(path, method, operation, base_url)
                if 'tags' in operation:
                    request['tags'] = operation['tags']
                requests.append(request)

        postman_collection['item'] = self.organize_by_tags(requests)
        
        # Log summary of circular references found
        if self.circular_refs:
            logger.info(f"Found {len(self.circular_refs)} circular references in the schema")
            
        return postman_collection

def main():
    parser = argparse.ArgumentParser(description='Convert Swagger/OpenAPI definition to Postman collection')
    parser.add_argument('--url', required=True, help='Swagger JSON URL')
    parser.add_argument('--header', action='append', help='Headers in format key:value')
    parser.add_argument('--output', default='postman_collection.json', help='Output file name')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    headers = {}
    if args.header:
        for header in args.header:
            key, value = header.split(':', 1)
            headers[key.strip()] = value.strip()
    
    try:
        converter = SwaggerToPostmanConverter(args.url, headers)
        postman_collection = converter.convert()
        
        with open(args.output, 'w') as f:
            json.dump(postman_collection, f, indent=2)
        
        print(f"Successfully converted Swagger to Postman collection: {args.output}")
    
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
