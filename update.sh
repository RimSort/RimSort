#!/bin/bash

# Detect the operating system
os=$(uname)

# Set the update source folder based on the OS
if [ "$os" = "Darwin" ]; then
	# macOS detected
	executable_name=RimSort.app
	grandparent_dir="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
	update_source_folder="${TMPDIR:-/tmp}"
	# Ensure the application is killed
	killall -q RimSort
else
	# Assume Linux if not macOS
	executable_name=RimSort.bin
	parent_dir="$(realpath .)"
	update_source_folder="/tmp/RimSort"
	# Ensure the application is killed
	killall -q $executable_name
fi

# Display a message indicating the update operation is starting in 5 seconds
read -tr 5 -p "Updating RimSort in 5 seconds. Press any key to cancel."

# Execute RimSort from the current directory
if [ "$os" = "Darwin" ]; then # macOS detected
	# Remove old installation
	rm -rf "${grandparent_dir}"
	# Move files from the update source folder to the current directory
	chmod +x "${update_source_folder}/${executable_name}/Contents/MacOS/RimSort" && chmod +x "${update_source_folder}/${executable_name}/Contents/MacOS/todds/todds" && mv "${update_source_folder}/${executable_name}" "${grandparent_dir}"
	open "${grandparent_dir}"
else # Assume Linux if not macOS
	# Remove old installation
	rm -rf "${parent_dir}"
	# Move files from the update source folder to the current directory
	chmod +x "${update_source_folder}/${executable_name}" && chmod +x "${update_source_folder}/todds/todds" && mv "${update_source_folder}" "${parent_dir}"
	cd "${parent_dir}" && ./$executable_name &
	cd "${parent_dir}" || echo "Failed to cd to ${parent_dir}" && exit 1
fi
