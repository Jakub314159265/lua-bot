import sys
from lupa import LuaRuntime

def execute_lua_code(lua_code):
    """Execute Lua code in a secure, restricted environment."""
    result = {"output": "", "error": None}
    
    try:
        # Create Lua runtime
        lua = LuaRuntime(unpack_returned_tuples=True)
        
        # Set up secure Lua environment with extensive restrictions
        lua.execute("""
            -- Clear all dangerous globals
            os = nil
            io = nil
            file = nil
            package = nil
            require = nil
            dofile = nil
            loadfile = nil
            load = nil
            loadstring = nil
            module = nil
            rawget = nil
            rawset = nil
            rawequal = nil
            rawlen = nil
            getmetatable = nil
            setmetatable = nil
            debug = nil
            collectgarbage = nil
            _G = nil

            -- Restrict coroutine functions
            coroutine = {
                create = coroutine.create,
                resume = coroutine.resume,
                status = coroutine.status,
                yield = coroutine.yield
            }

            -- Keep only safe string and math functions
            string = {
                byte = string.byte,
                char = string.char,
                find = string.find,
                format = string.format,
                len = string.len,
                lower = string.lower,
                match = string.match,
                rep = string.rep,
                reverse = string.reverse,
                sub = string.sub,
                upper = string.upper
            }

            -- Set up output capture
            local outputs = {}
            function print(...)
                local args = {...}
                local str_args = {}
                for i, v in ipairs(args) do
                    str_args[i] = tostring(v)
                end
                table.insert(outputs, table.concat(str_args, '\\t'))
            end

            function get_output()
                return table.concat(outputs, '\\n')
            end
        """)
        
        # Execute user code
        lua_result = lua.execute(lua_code)
        
        # Get captured output
        output = lua.eval("get_output()")
        if output and output.strip():
            result["output"] = output
        elif lua_result is not None:
            result["output"] = str(lua_result)
            
    except Exception as e:
        result["error"] = str(e)
    
    return result

def main():
    try:
        lua_code = sys.stdin.read().strip()
        if not lua_code:
            print("No Lua code provided")
            return
        
        result = execute_lua_code(lua_code)
        
        if result["error"]:
            print(f"Error: {result['error']}")
        elif result["output"]:
            print(result["output"])
        else:
            print("No output")
            
    except KeyboardInterrupt:
        print("Interrupted")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
