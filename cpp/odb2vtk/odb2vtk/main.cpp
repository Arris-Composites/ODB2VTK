#include <iostream>
#include <odb_API.h>    
#include <string.h>
#include <time.h>

#include "odb2vtk.h"

// --header --odbFile --instance --step --writeHistory --writePVD
enum class ArgumentType {
    HEADER,
    ODBFILE,
    INSTANCE,
    STEP,
    WRITEHISTORY,
    WRITEPVD,
};

int main(int argc, char* argv[]) {

    odb_initializeAPI();

    // Ok I tried to pull some argument parse libraries but their dependencies such as <algorithm> will give me
    // INT64_MAX: identifier not found
    // not sure why this is happening. Tried everything I can find online but none works
    // now I can't even #include <algorithm>
    // but fortunately, we don't need any 
    // here I just implement a simple parse logic
    // parse rules
    // --header --odbFile --instance --step --writeHistory --writePVD

    std::map<ArgumentType, std::vector<char*>> args_map;
    ArgumentType last = ArgumentType::HEADER;
    for (int i = 1; i < argc; i++)
    {
        char* c = argv[i];
        if (strcmp(c, "--header") == 0)
        {
            args_map[ArgumentType::HEADER] = std::vector<char*>();
            last = ArgumentType::HEADER;
            continue;
        }
        else if (strcmp(c, "--odbFile") == 0)
        {
            args_map[ArgumentType::ODBFILE] = std::vector<char*>();
            last = ArgumentType::ODBFILE;
            continue;
        }
        else if (strcmp(c, "--instance") == 0)
        {
            args_map[ArgumentType::INSTANCE] = std::vector<char*>();
            last = ArgumentType::INSTANCE;
            continue;
        }
        else if (strcmp(c, "--step") == 0)
        {
            args_map[ArgumentType::STEP] = std::vector<char*>();
            last = ArgumentType::STEP;
            continue;
        }
        else if (strcmp(c, "--writeHistory") == 0)
        {
            args_map[ArgumentType::WRITEHISTORY] = std::vector<char*>();
            last = ArgumentType::WRITEHISTORY;
            continue;
        }
        else if (strcmp(c, "--writePVD") == 0)
        {
            args_map[ArgumentType::WRITEPVD] = std::vector<char*>();
            last = ArgumentType::WRITEPVD;
            continue;
        }
        args_map[last].push_back(c);
    }

    if (args_map.find(ArgumentType::HEADER) == args_map.end())
    {
        std::cout << "--header argument not found." << std::endl;
        return -1;
    }

    if (args_map.find(ArgumentType::ODBFILE) == args_map.end())
    {
        std::cout << "--odbFile argument not found." << std::endl;
        return -1;
    }
    else
    {
        if (args_map[ArgumentType::ODBFILE].size() > 1)
        {
            std::cout << "ODB2VTK only takes one file at a time." << std::endl;
            return -1;
        }
    }


    try {

        // let's log execution time
        clock_t tStart = clock();

        odb2vtk converter(args_map[ArgumentType::ODBFILE].front(), "suffix");
        if (strcmp(args_map[ArgumentType::HEADER].front(), "1") == 0)
        {
            converter.ExtractHeader();
            std::cout << "Header file is complete." << std::endl;
        }
        else
        {
            // if not writing header file
            // then we are writing VTU file
            // arguments check 
            if (args_map.find(ArgumentType::INSTANCE) == args_map.end())
            {
                std::cout << "--instance argument not found." << std::endl;
                return -1;
            }
            if (args_map.find(ArgumentType::STEP) == args_map.end())
            {
                std::cout << "--step argument not found." << std::endl;
                return -1;
            }
            if (args_map.find(ArgumentType::WRITEHISTORY) == args_map.end())
            {
                std::cout << "--writeHistory argument not found." << std::endl;
                return -1;
            }

            // copy instance names array to odb2vtk
            std::vector<std::string> instance_names;
            for (const auto& instName : args_map[ArgumentType::INSTANCE])
            {
                instance_names.push_back(instName);
            }
            // copy step-frames array to odb2vtk
            std::map<std::string, std::vector<int>> step_frames;
            for (const auto& sf : args_map[ArgumentType::STEP])
            {
                auto str = std::string(sf);
                // step name and frame number are separated by :
                auto found = str.find(":");
                auto step_name = str.substr(0, found);
                if (step_name.length() == 0)
                {
                    std::cout << "make sure --step argument is formatted as <step_name>:0,1,2,3,4" << std::endl;
                    return -1;
                }
                step_frames[step_name] = std::vector<int>();
                std::string::size_type pre_pos = found + 1, pos = 0;
                // step argument must be in name:1,3,4,5 format
                // split string by , and convert them to int
                while ((pos = str.find(",", pos)) != std::string::npos)
                {
                    auto frame_number = str.substr(pre_pos, pos - pre_pos);
                    step_frames[step_name].push_back(std::stoi(frame_number));
                    pre_pos = ++pos;
                }
                step_frames[step_name].push_back(std::stoi(str.substr(pre_pos, pos - pre_pos))); // Last number
            }
            converter.ReadArgs(instance_names, step_frames);

            // write vtu files
            converter.WriteVTUFiles();

            std::cout << "Execution time: " << (clock() - tStart) / CLOCKS_PER_SEC << " seconds" << std::endl;
        }

    }
    catch (odb_BaseException& exc) {
        std::cout << "Abaqus error message: " << exc.UserReport().CStr() << std::endl;
    }
    catch (...) {
        std::cout << "Unknown Exception.\n";
    }
    odb_finalizeAPI();
    return 0;
}