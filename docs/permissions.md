It shouldnt't be possible for myself to review these changes and merging them to main, but twsta asked me to test the setup permissions.

I have setup my dummy-branch to test out, so I thought I would just make a file to describe the test for the permissions for the actual rimsort main branch.
And than I will do a pull request from dummy-branch to main upstream to test out and to see if something happens, with or without review from creators: Oceancabbage, twsta and CaptainArbitrary.
My intent was for this not to be the case. Contributors should not be able to merge their own PRs without a repo admin to review. I would like a bit of discussion in ⁠No Access before we allow such things.

Those of you whom I have granted "write" permission to in-repo ( @Chunnyluny, Win11 tester , @Lion , @cylian91 ) is so that you can learn/troubleshoot/work without the hassle of having to maintain a fork. This grants you privileges to do most things in-repo such as make your own branches, merge branches to branches. Unless I made a mistake in my configuration of permissions, you do not have the ability to review and merge your own PRs as it requires administrator review + approval + merge to merge to main branch. You guys can think of this as a sort of "probationary role", as you should not have access to main branch directly without oversight. This decision is nothing personal on my part, and my intent is not to inhibit you guys at all, but rather provide a clear chain of command in regards to how the project progresses. Anybody who is actively willing to do such things for the project is entitled to this "probationary role" - all you need to do is request it from @creator .

Currently, the only "admins" for the project are @creator, and @CaptainArbitrary, thus the 3 of us are the only people who should be merging to main.

The reason why I have granted admin to @CaptainArbitrary is because I have seen him prove his ability with his feedback, work, and overall ability with not just his contributions to the project, but also his own work separate from RimSort. He has also provided his own hardware to produce builds for MacOS arm64.

The request is: Can you please make a test PR with something simple, and try to merge it to main yourself? This should NOT be possible currently.