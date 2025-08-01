import sys
from lupa import LuaRuntime


def execute_lua_code(lua_code):
    """Execute Lua code in a secure, restricted environment."""
    result = {"output": "", "error": None}

    try:
        # Create Lua runtime
        lua = LuaRuntime(unpack_returned_tuples=True,
                         register_eval=False, register_builtins=False)

        # set up Lua 'preamble' (like in LaTeX lmao)
        lua.execute("""
            -- Clear all dangerous globals
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
            
            -- restrict os
            os = {
                time = os.time,
                date = os.date,
                clock = os.clock
            }

            -- restrict coroutine
            coroutine = {
                create = coroutine.create,
                resume = coroutine.resume,
                running = coroutine.running,
                wrap = coroutine.wrap,
                status = coroutine.status,
                yield = coroutine.yield,
                close = coroutine.close
            }
            
            -- Somone told me that gsub can be dangerous when it can be used on functions so...
            local function safe_gsub(s, pattern, repl, n)
                local t = type(repl)
                if t ~= "string" and t ~= "table" then
                    error("gsub: replacement must be string or table, functions not allowed")
                end
                return string.gsub(s, pattern, repl, n)
            end
            
            -- Keep only safe string functions
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
                upper = string.upper,
                gmatch = string.gmatch,
                gsub = safe_gsub
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

        # execute code
        lua_result = lua.execute(lua_code)

        # get captured output
        output = lua.eval("get_output()")
        
        if output and lua_result is not None:
            result["output"] = output + "\n" + str(lua_result)
        elif output:
            result["output"] = output
        elif lua_result is not None:
            result["output"] = str(lua_result)

    except Exception as e:
        error_msg = str(e).replace('[string "<python>"]', 'stdin')
        result["error"] = error_msg

    return result


def main():
    try:
        lua_code = sys.stdin.read().strip()
        if not lua_code:
            print("No Lua code provided", file=sys.stderr)
            return

        result = execute_lua_code(lua_code)

        if result["error"]:
            # print it in stderr to make it an error
            print(result['error'], file=sys.stderr)
        elif result["output"]:
            print(result["output"])

    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
